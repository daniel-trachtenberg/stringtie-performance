#include "gclib/GSam.h"
#include "htslib/hts_log.h"
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <vector>

static size_t checked=0;
static void check(const std::vector<uint8_t>& bytes, size_t length) {
  bam1_t* raw=bam_init1();
  assert(bam_set1(raw, 4, "read", BAM_FUNMAP, -1, -1, 0,
                  0, NULL, -1, -1, 0, 0, NULL, NULL, length)>=0);
  memcpy(bam_get_aux(raw), bytes.data(), length);
  raw->l_data+=length;
  GSamRecord record(raw);
  const char* tags[]={"NH", "HI", "NM", "nM", "YC", "YK", "MD", "XS", "ts", "ZS", "ZF", "ZZ", "AA"};
  for (int repeat=0;repeat<2;++repeat) {
    for (const char* tag:tags) {
      errno=EDOM;
      uint8_t* expected=bam_aux_get(raw, tag);
      int expected_errno=errno;
      errno=EDOM;
      uint8_t* actual=record.find_tag(tag);
      if (actual!=expected || errno!=expected_errno) {
        fprintf(stderr,"Mismatch len=%zu tag=%s pointers=%td/%td errno=%d/%d\n",length,tag,
          actual ? actual-raw->data : -1,expected ? expected-raw->data : -1,errno,expected_errno);
        abort();
      }
      ++checked;
    }
    for (int i=0;i<GSamRecord::AUX_CACHE_SIZE;++i) {
      GSamRecord::AuxCacheIndex tag=static_cast<GSamRecord::AuxCacheIndex>(i);
      assert(record.tag_int(tags[i],123)==record.tag_int(tag,123));
      double expected=record.tag_float(tags[i]);
      double actual=record.tag_float(tag);
      assert(memcmp(&expected,&actual,sizeof(double))==0);
      assert(record.tag_str(tags[i])==record.tag_str(tag));
      assert(record.tag_char1(tags[i])==record.tag_char1(tag));
      checked+=4;
    }
    assert(record.spliceStrand()==record.assemblyStrand());
    ++checked;
  }
}
int main() {
  hts_set_log_level(HTS_LOG_OFF);
  std::vector<uint8_t> data={
    'N','H','C',3,'H','I','c',1,'N','M','S',4,0,
    'n','M','s',0xFF,0xFF,'Y','C','I',1,0,0,0,
    'Y','K','f',0,0,0,0,'M','D','Z','2','A','3',0,
    'X','S','A','+','t','s','A','-','Z','S','Z','x',0,
    'Z','F','d',0,0,0,0,0,0,0,0,'Z','Z','H','A','A',0,
    'N','H','C',9,'Z','Z','B','i',2,0,0,0,1,0,0,0,2,0,0,0};
  for(size_t length=0;length<=data.size();++length) check(data,length);
  for(size_t i=0;i<data.size();++i) {
    std::vector<uint8_t> mutated=data;
    mutated[i]='?';
    // Corrupt only tag/type/string bytes, avoiding gigantic array counts.
    if(i>data.size()-13 && i<data.size()-8) continue;
    check(mutated,mutated.size());
  }
  fprintf(stdout,"Validated %zu tag lookups and errno results against HTSlib\n",checked);
}
