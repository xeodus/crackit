#pragma once
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

inline std::string overlap_key(const std::string &word) {
    std::string result;
    for (unsigned char c : word) {
        if (c >= 128) result += char(c);
        else if (std::isalnum(c)) result += char(std::tolower(c));
    }
    return result;
}
struct OverlapAlignment { bool found=false; size_t trim=0; size_t anchor_tokens=0; };

// Require a unique exact suffix anchor near the physical handoff. Approximate
// Whisper timestamps only bound the search; they do not delete new words.
// Unknown/changed spellings are not substituted to manufacture an anchor.
template <class Word>
OverlapAlignment align_overlap(const std::vector<Word>& words,
                               const std::vector<Word>& committed_tail,
                               int64_t committed_end) {
    size_t maximum=std::min<size_t>(8,committed_tail.size());
    for (size_t count=maximum;count>=2;--count) {
        size_t matches=0,last_trim=0;
        for (size_t begin=0;begin+count<=words.size();++begin) {
            int64_t anchor_end=words[begin+count-1].end;
            if (anchor_end<committed_end-2000 || anchor_end>committed_end+2000) continue;
            bool equal=true;
            for (size_t j=0;j<count;++j) {
                auto old_key=overlap_key(committed_tail[committed_tail.size()-count+j].text);
                auto new_key=overlap_key(words[begin+j].text);
                if (old_key.empty() || old_key!=new_key) { equal=false;break; }
            }
            if (equal) { ++matches;last_trim=begin+count; }
        }
        if (matches==1) return {true,last_trim,count};
        if (matches>1) return {}; // Ambiguity must remain explicit, not guessed.
    }
    return {};
}
