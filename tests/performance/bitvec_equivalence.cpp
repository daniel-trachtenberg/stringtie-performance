#include "gclib/GBitVec.h"
#include <cassert>
#include <cstdint>
#include <cstdio>

static uint64_t state=123456789;
static uint64_t random_value() {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

int main() {
    unsigned long checks=0;
    for(unsigned a_size=0;a_size<194;a_size++) {
        for(unsigned b_size=0;b_size<194;b_size++) {
            for(int pattern=0;pattern<8;pattern++) {
                GBitVec a(a_size), b(b_size);
                for(unsigned i=0;i<a_size;i++)
                    a[i]=(pattern==1 || pattern==3 || (pattern>=4 && (random_value()&1)));
                for(unsigned i=0;i<b_size;i++)
                    b[i]=(pattern==2 || pattern==3 || (pattern>=4 && (random_value()&1)));
                assert(a.contains(b)==((a&b)==b));
                assert(b.contains(a)==((b&a)==a));
                GBitVec joined=a|b;
                GBitVec inplace=a;
                inplace|=b;
                assert(inplace==joined);
                a.reserve(1024);
                a.clear();
                a.resize(a_size);
                assert(a.contains(b)==((a&b)==b));
                ++checks;
            }
        }
    }
    std::printf("PASS: %lu vector pairs, four equivalence checks per pair\n",checks);
}
