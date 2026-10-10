#include "overlap_alignment.h"
#include <cassert>
struct Word { std::string text; int64_t start,end; };
int main() {
    std::vector<Word> tail={{" must",24000,24200},{" not",24200,24400},{" save",24400,24600}};
    // Newly decoded word timestamps can drift into committed time. They must
    // survive when the lexical handoff establishes that they follow the anchor.
    std::vector<Word> next={{"must",23900,24000},{" not",24000,24100},{" save",24100,24200},
                           {" raw",24200,24400},{" audio.",24400,24600}};
    auto a=align_overlap(next,tail,24600);assert(a.found&&a.trim==3&&a.anchor_tokens==3);
    assert(next[a.trim].text==" raw");
    std::vector<Word> unknown={{" unrelated",24000,24200},{" words",24200,24400}};
    assert(!align_overlap(unknown,tail,24600).found);
    auto far=next;for(auto &w:far){w.start+=17000;w.end+=17000;}
    assert(!align_overlap(far,tail,24600).found);
    std::vector<Word> short_tail={{" name",24000,24200}};
    assert(!align_overlap(next,short_tail,24600).found);
    auto duplicate=next;duplicate.insert(duplicate.end(),next.begin(),next.end());
    assert(!align_overlap(duplicate,tail,24600).found);
    std::vector<Word> punctuation_tail={{" budget",24000,24200},{" is",24200,24400},{" $12,000.",24400,24600}};
    std::vector<Word> punctuation_new={{" Budget",24000,24200},{" is",24200,24400},{" 12000",24400,24600},{" Mira",24600,25000}};
    assert(align_overlap(punctuation_new,punctuation_tail,24600).trim==3);
}
