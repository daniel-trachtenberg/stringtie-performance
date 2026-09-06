#ifndef STRINGTIE_READ_PAIR_INDEX_H
#define STRINGTIE_READ_PAIR_INDEX_H

#include "GHashMap.hh"

// Pending mates are identified by exactly the same three fields as the former
// name-position-hit string. Keep the numeric fields numeric, and cache the hash
// so a table resize never scans pending names again. Only pending names are owned.
class ReadPairIndex {
    struct Key {
        const char* name;
        int position;
        int hit;
        uint64_t hash;
    };
    struct Hash {
        uint64_t operator()(const Key& key) const { return key.hash; }
    };
    struct Equal {
        bool operator()(const Key& a, const Key& b) const {
            return a.hash == b.hash && a.position == b.position &&
                   a.hit == b.hit && strcmp(a.name, b.name) == 0;
        }
    };
    GHashMap<Key, int, Hash, Equal> entries;

    static Key makeKey(const char* name, int position, int hit) {
        const uint64_t seed = (uint64_t(uint32_t(position)) << 32) | uint32_t(hit);
        Key key = {name, position, hit, wyhash(name, strlen(name), seed, _wyp)};
        return key;
    }

public:
    ReadPairIndex() = default;
    ReadPairIndex(const ReadPairIndex&) = delete;
    ReadPairIndex& operator=(const ReadPairIndex&) = delete;
    ~ReadPairIndex() { Clear(); }

    // As with GHash::Add, a duplicate retains the first stored read index.
    void Add(const char* name, int position, int hit, int read_index) {
        Key key = makeKey(name, position, hit);
        int absent = 0;
        const uint64_t slot = entries.put(key, &absent);
        if (absent == 1) {
            entries.key(slot).name = Gstrdup(name);
            entries.value(slot) = read_index;
        }
    }

    // Lookup and erase once; -1 cannot be a valid readlist index.
    int Take(const char* name, int position, int hit) {
        const uint64_t slot = entries.get(makeKey(name, position, hit));
        if (slot == entries.end()) return -1;
        const int read_index = entries.value(slot);
        GFREE(entries.key(slot).name);
        entries.del(slot);
        return read_index;
    }

    void Clear() {
        for (uint64_t i = 0; i != entries.n_buckets(); ++i) {
            if (entries._used(i)) GFREE(entries.key(i).name);
        }
        entries.Clear();
    }
};
#endif
