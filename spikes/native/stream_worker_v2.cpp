// Persistent, bounded PCM decoder. Input is a file or '-' (stdin), s16le/16k/mono.
// JSONL contains replaceable partials, endpoint finals, and timestamped words.
#include "whisper.h"
#include "overlap_alignment.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

static std::string quoted(const std::string&s){
    std::ostringstream o;o<<'"';for(unsigned char c:s){
        if(c=='"'||c=='\\')o<<'\\'<<c;else if(c=='\n')o<<"\\n";
        else if(c=='\r')o<<"\\r";else if(c=='\t')o<<"\\t";else if(c>=32)o<<c;
    }o<<'"';return o.str();
}
struct Word{std::string text;int64_t start,end;};
static std::vector<Word> decode(whisper_context*ctx,std::vector<float>&audio,int64_t start,
                               const std::string&prompt,double&elapsed){
    auto p=whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    p.n_threads=4;p.language="en";p.no_context=true;p.temperature_inc=0;p.greedy.best_of=1;
    p.print_realtime=false;p.print_progress=false;p.print_timestamps=false;p.print_special=false;
    p.token_timestamps=true;p.split_on_word=true;p.no_timestamps=false;
    p.initial_prompt=prompt.empty()?nullptr:prompt.c_str();
    auto begin=std::chrono::steady_clock::now();
    if(whisper_full(ctx,p,audio.data(),int(audio.size())))throw std::runtime_error("Decode failed");
    elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
    std::vector<Word> words;Word current{"",-1,-1};
    auto flush=[&](){if(!current.text.empty()&&current.start>=0&&current.end>=current.start)words.push_back(current);current={"",-1,-1};};
    for(int i=0;i<whisper_full_n_segments(ctx);++i){
        for(int j=0;j<whisper_full_n_tokens(ctx,i);++j){
            if(whisper_full_get_token_id(ctx,i,j)>=whisper_token_eot(ctx))continue;
            std::string token=whisper_full_get_token_text(ctx,i,j);
            auto t=whisper_full_get_token_data(ctx,i,j);
            if(!token.empty()&&std::isspace(static_cast<unsigned char>(token[0])))flush();
            if(current.start<0&&t.t0>=0)current.start=start+t.t0*10;
            if(t.t1>=0)current.end=start+t.t1*10;
            current.text+=token;
        }flush();
    }
    words.erase(std::remove_if(words.begin(),words.end(),[](const Word&w){
        return w.text.find('[')!=std::string::npos || w.text.find(']')!=std::string::npos;
    }),words.end());return words;
}
int main(int argc,char**argv){
    if(argc<4||argc>5){std::cerr<<"Usage: whisper-stream MODEL VAD PCM_FILE_OR_STDIN [VOCABULARY]\n";return 2;}
    std::ifstream file;std::istream*input=&std::cin;
    if(std::string(argv[3])!="-"){file.open(argv[3],std::ios::binary);if(!file)return 2;input=&file;}
    auto cp=whisper_context_default_params();cp.use_gpu=false;
    auto ctx=whisper_init_from_file_with_params(argv[1],cp);if(!ctx)return 1;
    auto vp=whisper_vad_default_context_params();vp.use_gpu=false;vp.n_threads=1;
    auto vad=whisper_vad_init_from_file_with_params(argv[2],vp);if(!vad){whisper_free(ctx);return 1;}
    std::cout<<"{\"type\":\"ready\"}\n"<<std::flush;
    std::string prompt=argc==5?argv[4]:"";
    int64_t processed=0,window_start=0,committed_end=-1,last_decode=0,utterance=0,revision=0;
    int speech_frames=0,silent_frames=0;bool active=false;
    std::deque<float> pre;std::vector<float> window;window.reserve(480000);
    std::vector<Word> committed_tail;
    size_t max_samples=0;int decode_count=0;double total_decode=0;
    auto emit=[&](const std::string&type,const std::vector<Word>&ws,double elapsed,const std::string&reason){
        std::string text;for(const auto&w:ws)text+=w.text;
        std::cout<<"{\"type\":"<<quoted(type)<<",\"segment_id\":"<<quoted("u"+std::to_string(utterance))
                 <<",\"revision\":"<<revision++<<",\"audio_processed_ms\":"<<processed/16
                 <<",\"start_ms\":"<<(ws.empty()?window_start/16:ws.front().start)
                 <<",\"end_ms\":"<<(ws.empty()?processed/16:ws.back().end)
                 <<",\"decode_ms\":"<<elapsed<<",\"reason\":"<<quoted(reason)<<",\"text\":"<<quoted(text)<<",\"words\":[";
        for(size_t i=0;i<ws.size();++i){if(i)std::cout<<',';std::cout<<"{\"text\":"<<quoted(ws[i].text)<<",\"start_ms\":"<<ws[i].start<<",\"end_ms\":"<<ws[i].end<<'}';}
        std::cout<<"]}\n"<<std::flush;
    };
    auto run_decode=[&](bool final,bool boundary,const std::string&reason){
        if(window.size()<3200)return;
        double elapsed=0;auto ws=decode(ctx,window,window_start/16,prompt,elapsed);
        ++decode_count;total_decode+=elapsed;
        if(!committed_tail.empty()){
            auto alignment=align_overlap(ws,committed_tail,committed_end);
            if(!alignment.found){
                if(!final){emit("partial",ws,elapsed,"overlap_alignment_pending");last_decode=processed;return;}
                emit("gap",{},elapsed,"overlap_alignment_unresolved");
                emit("final",{},0,"overlap_alignment_unresolved");
                ++utterance;revision=0;committed_tail.clear();committed_end=-1;
                window.clear();pre.clear();active=false;speech_frames=0;silent_frames=0;
                whisper_vad_reset_state(vad);last_decode=processed;return;
            }
            ws.erase(ws.begin(),ws.begin()+alignment.trim);
        }
        const int64_t cutoff=boundary?(window_start+int64_t(window.size()))/16-2000:processed/16;
        ws.erase(std::remove_if(ws.begin(),ws.end(),[&](const Word&w){return boundary&&w.end>cutoff;}),ws.end());
        // Final with empty text closes a partial without promoting markers.
        emit(final?"final":"partial",ws,elapsed,reason);
        if(final){
            if(!ws.empty())committed_end=ws.back().end;
            ++utterance;revision=0;
        }
        if(boundary){
            if(ws.empty()){
                emit("gap",{},0,"No timestamp-aligned completed region at window boundary");
                window.clear();pre.clear();active=false;speech_frames=0;silent_frames=0;
                committed_tail.clear();committed_end=-1;whisper_vad_reset_state(vad);
            }else{
                committed_tail.insert(committed_tail.end(),ws.begin(),ws.end());
                if(committed_tail.size()>8)committed_tail.erase(committed_tail.begin(),committed_tail.end()-8);
                int64_t keep_start=std::max(window_start,(committed_end-2000)*16);
                size_t trim=std::min(window.size(),size_t(keep_start-window_start));
                window.erase(window.begin(),window.begin()+trim);window_start+=trim;
            }
        }else if(final){committed_tail.clear();committed_end=-1;}
        last_decode=processed;
    };
    try{
        char raw[1024];
        while(input->read(raw,sizeof(raw))||input->gcount()){
            int n=int(input->gcount());if(n%2)throw std::runtime_error("Odd PCM byte count");
            std::vector<float> frame(512,0);
            for(int i=0;i<n/2;++i){uint16_t v=uint8_t(raw[2*i])|(uint16_t(uint8_t(raw[2*i+1]))<<8);frame[i]=float(int16_t(v))/32768;}
            if(!whisper_vad_detect_speech_no_reset(vad,frame.data(),512))throw std::runtime_error("VAD failed");
            float probability=whisper_vad_n_probs(vad)>0?whisper_vad_probs(vad)[whisper_vad_n_probs(vad)-1]:0;
            bool speech=probability>=0.5f;processed+=n/2;
            for(int i=0;i<n/2;++i){pre.push_back(frame[i]);if(pre.size()>8000)pre.pop_front();}
            if(!active){
                speech_frames=speech?speech_frames+1:0;
                if(speech_frames>=7){active=true;silent_frames=0;window.assign(pre.begin(),pre.end());window_start=processed-window.size();last_decode=processed;}
            }else{
                window.insert(window.end(),frame.begin(),frame.begin()+n/2);
                silent_frames=speech?0:silent_frames+1;
                max_samples=std::max(max_samples,window.size());
                if(silent_frames>=19){
                    // Keep 300ms trailing padding, not the entire endpoint silence.
                    size_t tail=std::min(window.size(),size_t(4800));window.resize(window.size()-tail);
                    run_decode(true,false,"vad_endpoint");window.clear();active=false;speech_frames=0;
                    whisper_vad_reset_state(vad);pre.clear();
                }else if(window.size()>=479488){run_decode(true,true,"window_boundary");}
                else if(processed-last_decode>=16000){run_decode(false,false,"periodic");}
            }
        }
        if(active)run_decode(true,false,"end_of_input");
        std::cout<<"{\"type\":\"summary\",\"audio_seconds\":"<<double(processed)/16000
                 <<",\"max_audio_samples\":"<<max_samples<<",\"decode_count\":"<<decode_count
                 <<",\"total_decode_ms\":"<<total_decode<<"}\n";
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';whisper_vad_free(vad);whisper_free(ctx);return 1;}
    whisper_vad_free(vad);whisper_free(ctx);return 0;
}
