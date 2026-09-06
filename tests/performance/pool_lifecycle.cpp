#include "bundle.h"
#include <cassert>
#include <cstdio>
bool mergeMode=false;
bool ballgown=false;
bool genNascent=false;
int main() {
  for(int mode=0;mode<2;++mode) {
    mergeMode=mode;
    BundleData bundle;
    for(int cycle=0;cycle<4;++cycle) {
      for(int i=0;i<5000;++i) {
        TAlnInfo* info=mergeMode ? new TAlnInfo("transcript",i) : NULL;
        CReadAln* r=bundle.newRead(-1,3,i+1,i+10,info);
        assert(r->start==unsigned(i+1) && r->end==unsigned(i+10));
        assert(r->strand==-1 && r->nh==3 && r->len==0 && r->read_count==0);
        assert(!r->unitig && !r->longread && r->sort_tiebreaker==0);
        assert(!r->pair_count.Count() && !r->pair_idx.Count() && !r->segs.Count() && !r->juncs.Count());
        assert(!r->aligned_polyT && !r->aligned_polyA && !r->unaligned_polyT && !r->unaligned_polyA);
        assert(r->tinfo==info);
        r->len=99; r->read_count=1.25f; r->unitig=true; r->longread=true; r->sort_tiebreaker=123;
        r->aligned_polyT=65535; r->aligned_polyA=9; r->unaligned_polyT=9; r->unaligned_polyA=9;
        float count=1.5; r->pair_count.Add(count); r->pair_idx.Add(i);
        GSeg segment(i+1,i+10); r->segs.Add(segment);
        CJunction* j=new CJunction(i,i+3,1); bundle.junction.Add(j); r->juncs.Add(j);
        if(i%100==0) r->segs.setCapacity(128);
        bundle.readlist.Add(r);
      }
      bundle.Clear();
      assert(bundle.readlist.Count()==0 && bundle.spare_reads.Count()==4096);
      for(int i=0;i<bundle.spare_reads.Count();++i) {
        CReadAln* r=bundle.spare_reads[i];
        assert(r->segs.Capacity()<=64 && r->juncs.Capacity()<=64);
        assert(r->pair_count.Capacity()<=64 && r->pair_idx.Capacity()<=64);
        assert(r->tinfo==NULL && r->juncs.Count()==0);
      }
    }
  }
  printf("Read pool: 40000 populated/reset lifecycles across assembly and merge passed\n");
}
