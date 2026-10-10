// Bounded causal replay experiment, not a production streaming recognizer.
// Holds one Whisper context, decodes cumulative <=30-second PCM prefixes.
// Compares consecutive hypotheses; agreed prefixes may still change later.
#include "whisper.h"
#include <algorithm>
#include <chrono>
#include <cctype>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

static std::string json_string(const std::string &s) {
    std::ostringstream out; out << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out << '\\' << c; }
        else if (c == '\n') out << "\\n";
        else if (c == '\r') out << "\\r";
        else if (c == '\t') out << "\\t";
        else if (c < 32) out << ' ';
        else out << c;
    }
    out << '"'; return out.str();
}
static std::vector<std::string> words(const std::string &s) {
    std::vector<std::string> result; std::istringstream input(s); std::string word;
    while (input >> word) result.push_back(word);
    return result;
}
static std::string normalized(std::string s) {
    std::string out;
    for (unsigned char c : s) if (std::isalnum(c) || c >= 128) out += char(std::tolower(c));
    return out;
}
static std::string joined(const std::vector<std::string> &items, size_t count) {
    std::ostringstream out;
    for (size_t i=0; i<count; ++i) { if (i) out << ' '; out << items[i]; }
    return out.str();
}
int main(int argc, char **argv) {
    if (argc != 4) { std::cerr << "Usage: whisper-replay MODEL RAW_16KHZ_MONO_S16LE cpu|metal\n"; return 2; }
    const std::string backend = argv[3];
    if (backend != "cpu" && backend != "metal") return 2;
    std::ifstream input(argv[2], std::ios::binary);
    std::vector<char> raw((std::istreambuf_iterator<char>(input)), {});
    if (!input || raw.empty() || raw.size()%2 || raw.size()>16000*2*30) {
        std::cerr << "Invalid raw PCM; bounded to 30 seconds\n"; return 2;
    }
    std::vector<float> samples(raw.size()/2);
    for (size_t i=0; i<samples.size(); ++i) {
        uint16_t bits = uint8_t(raw[2*i]) | (uint16_t(uint8_t(raw[2*i+1])) << 8);
        samples[i] = float(int16_t(bits))/32768.0f;
    }
    auto context_params = whisper_context_default_params(); context_params.use_gpu = backend == "metal";
    const auto load_start = std::chrono::steady_clock::now();
    whisper_context *context = whisper_init_from_file_with_params(argv[1], context_params);
    if (!context) return 1;
    const double load_ms = std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-load_start).count();
    auto params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = 4; params.language = "en"; params.no_context = true;
    params.print_realtime = false; params.print_progress = false; params.print_timestamps = false;
    params.print_special = false;
    // Match the controlled CLI's deterministic decode settings. Timestamp tokens
    // remain enabled even though timestamps aren't printed.
    params.no_timestamps = false; params.temperature_inc = 0.0f;
    params.greedy.best_of = 1;
    std::vector<std::string> previous; std::string prior_agreed;
    int revisions = 0; const size_t step = 16000*2;
    for (size_t count = std::min(step,samples.size()); ; count = std::min(count+step,samples.size())) {
        const auto start = std::chrono::steady_clock::now();
        if (whisper_full(context, params, samples.data(), int(count)) != 0) { whisper_free(context); return 1; }
        const double decode_ms = std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        std::string hypothesis;
        for (int i=0; i<whisper_full_n_segments(context); ++i) hypothesis += whisper_full_get_segment_text(context,i);
        auto current = words(hypothesis); size_t common = 0;
        while (common < current.size() && common < previous.size()
               && normalized(current[common]) == normalized(previous[common])) ++common;
        std::string agreed = joined(current,common);
        auto prior_words = words(prior_agreed);
        bool revised = common < prior_words.size();
        for (size_t i=0; !revised && i<prior_words.size(); ++i)
            if (normalized(current[i]) != normalized(prior_words[i])) revised = true;
        if (revised) ++revisions;
        std::cout << "{\"audio_available_seconds\":" << double(count)/16000
                  << ",\"decode_ms\":" << decode_ms << ",\"model_load_ms\":" << load_ms
                  << ",\"hypothesis\":" << json_string(hypothesis)
                  << ",\"agreed_prefix\":" << json_string(agreed)
                  << ",\"agreed_prefix_revisions\":" << revisions
                  << ",\"final_snapshot\":" << (count==samples.size()?"true":"false") << "}\n" << std::flush;
        previous = current; prior_agreed = agreed;
        if (count == samples.size()) break;
    }
    whisper_free(context); return 0;
}
