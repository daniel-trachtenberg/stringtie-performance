#include "read_pair_index.h"
#include "gclib/GStr.h"
#include <cassert>
#include <climits>
#include <cstdio>
#include <random>
#include <string>
#include <vector>
struct Key { std::string name; int pos; int hit; };
static GStr oldKey(const Key& k) {
  GStr value(k.name.c_str()); value+='-'; value+=k.pos; value+=".="; value+=k.hit;
  return value;
}
int main() {
  ReadPairIndex next;
  GHash<int> old;
  std::mt19937 rng(9062026);
  std::vector<Key> keys;
  const int extremes[]={INT_MIN, -1, 0, 1, 2, INT_MAX};
  // Include signed extremes without names that intentionally collide in the old encoding.
  for(int p:extremes) for(int h:extremes) keys.push_back({"extreme",p,h});
  const char* names[]={"x", "x-", "x--", "x-1.=0", "a.=2-3.=4", "", "read/1", "read/2"};
  for(const char* name:names) for(int h:extremes) keys.push_back({name,123,h});
  for(int i=0;i<10000;++i) keys.push_back({"read-"+std::to_string(i)+".=suffix",int(rng()%INT_MAX)+1,int(rng())});
  size_t checks=0;
  for(size_t i=0;i<keys.size();++i) {
    GStr key=oldKey(keys[i]);
    old.Add(key.chars(),int(i));
    next.Add(keys[i].name.c_str(),keys[i].pos,keys[i].hit,int(i));
  }
  for(int step=0;step<100000;++step) {
    const Key& k=keys[rng()%keys.size()];
    GStr key=oldKey(k);
    unsigned action=rng()%10;
    if(action<5) {
      int value=int(rng()%INT_MAX);
      old.Add(key.chars(),value); next.Add(k.name.c_str(),k.pos,k.hit,value);
    } else {
      const int* p=old[key.chars()];
      int expected=p ? *p : -1;
      int actual=next.Take(k.name.c_str(),k.pos,k.hit);
      assert(expected==actual);
      old.Remove(key.chars());
      ++checks;
    }
    if(step%16001==16000) { old.Clear(); next.Clear(); }
  }
  old.Clear(); next.Clear();
  for(int i=0;i<2000;++i) {
    std::string storage="ephemeral"+std::to_string(i);
    Key k={storage,100,INT_MIN};
    next.Add(storage.c_str(),100,INT_MIN,i);
    storage.assign(storage.size(),'x');
    assert(next.Take(k.name.c_str(),100,INT_MIN)==i);
    ++checks;
  }
  for(const Key& k:keys) {
    GStr key=oldKey(k); const int* p=old[key.chars()];
    assert(next.Take(k.name.c_str(),k.pos,k.hit)==(p?*p:-1));
    ++checks;
  }
  printf("ReadPairIndex: %zu successful differential/ownership checks\n",checks);
}
