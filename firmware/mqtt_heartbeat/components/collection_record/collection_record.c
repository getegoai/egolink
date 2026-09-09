#include "collection_record.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "mbedtls/sha256.h"

bool collection_record_ascii_xhh(const uint8_t *input, size_t input_length,
    char *output, size_t output_capacity, size_t *output_length,
    bool *truncated)
{
    static const char hex[]="0123456789ABCDEF";
    if(!output || output_capacity==0U || !output_length || !truncated ||
       (!input && input_length!=0U)) return false;
    size_t used=0U;
    *output_length=0U;
    *truncated=false;
    output[0]='\0';
    for(size_t index=0U;index<input_length;index++) {
        const uint8_t byte=input[index];
        const bool literal=(byte>=(uint8_t)' ' && byte<=(uint8_t)'~' &&
                            byte!=(uint8_t)'\\') ||
                           byte==(uint8_t)'\r' || byte==(uint8_t)'\n' ||
                           byte==(uint8_t)'\t';
        const size_t width=literal?1U:4U;
        if(width>=output_capacity-used) {
            *truncated=true;
            break;
        }
        if(literal) output[used++]=(char)byte;
        else {
            output[used++]='\\';
            output[used++]='x';
            output[used++]=hex[byte>>4];
            output[used++]=hex[byte&UINT8_C(0x0F)];
        }
    }
    output[used]='\0';
    *output_length=used;
    return true;
}

static uint32_t crc32(const unsigned char *p, size_t n)
{
    uint32_t c=~0U;
    while(n--) { c^=*p++; for(unsigned b=0;b<8;b++) c=(c>>1)^(0xEDB88320U & (0U-(c&1U))); }
    return ~c;
}
static bool safe_id(const char *s)
{
    if(!s || !*s || strlen(s)>128) return false;
    for(;*s;s++) if(!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||strchr("._:-",*s))) return false;
    return true;
}
size_t collection_record_frame(const cJSON *o, char *frame, size_t capacity)
{
    const cJSON *id=cJSON_GetObjectItemCaseSensitive(o,"observation_id");
    const cJSON *seq=cJSON_GetObjectItemCaseSensitive(o,"sequence_id");
    if(!cJSON_IsString(id)||!safe_id(id->valuestring)||!cJSON_IsNumber(seq)||seq->valuedouble<0||seq->valuedouble>4294967295.0||floor(seq->valuedouble)!=seq->valuedouble) return 0;
    char *json=cJSON_PrintUnformatted(o); if(!json) return 0;
    size_t bytes=strlen(json);
    int n=snprintf(frame,capacity,"EGLK/1 type=event id=%s seq=%u len=%u crc32=%08X\ncontent-type=application/json;profile=egolink.collection.v1\n\n%s",
        id->valuestring,(unsigned)seq->valuedouble,(unsigned)bytes,(unsigned)crc32((const unsigned char*)json,bytes),json);
    cJSON_free(json);
    return n>0 && (size_t)n<capacity ? (size_t)n : 0;
}
bool collection_record_identity(const void *frame, size_t length, char *id, size_t capacity)
{
    const char *s=frame; const char prefix[]="EGLK/1 type=event id=";
    if(!s || !id || length<sizeof(prefix)||memcmp(s,prefix,sizeof(prefix)-1)) return false;
    size_t i=sizeof(prefix)-1,n=0;
    while(i<length && s[i]!=' ') { if(n+1>=capacity) return false; id[n++]=s[i++]; }
    id[n]=0; return i<length && safe_id(id);
}
static bool unique_keys(const cJSON *o)
{
    if(cJSON_IsObject(o)) for(const cJSON *a=o->child;a;a=a->next)
        for(const cJSON *b=a->next;b;b=b->next) if(!strcmp(a->string,b->string)) return false;
    for(const cJSON *a=o->child;a;a=a->next) if(!unique_keys(a)) return false;
    return true;
}
static bool equals(const cJSON *o,const char *key,const char *expected)
{
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    return cJSON_IsString(v) && strcmp(v->valuestring,expected)==0;
}
bool collection_record_ack_matches(const void *frame,size_t length,const char *device,
    const void *response,size_t response_length)
{
    if(!frame||!device||!response||!response_length||response_length>8192) return false;
    char id[129],hash[65]; unsigned char digest[32];
    if(!collection_record_identity(frame,length,id,sizeof(id)) || mbedtls_sha256(frame,length,digest,0)) return false;
    for(size_t i=0;i<32;i++) snprintf(hash+2*i,3,"%02x",digest[i]);
    const char *end=NULL;
    cJSON *root=cJSON_ParseWithLengthOpts(response,response_length,&end,false);
    bool exact=end!=NULL;
    const char *limit=(const char*)response+response_length;
    while(exact && end<limit && (*end==' '||*end=='\n'||*end=='\r'||*end=='\t')) ++end;
    exact=exact && end==limit;
    const cJSON *ack=cJSON_GetObjectItemCaseSensitive(root,"delivery_ack");
    const cJSON *time=cJSON_GetObjectItemCaseSensitive(ack,"ack_time_ms");
    const cJSON *ack_id=cJSON_GetObjectItemCaseSensitive(ack,"ack_id");
    bool ok=root && exact && unique_keys(root) &&
        equals(ack,"contract_version","egolink.persistent_priority_outbox.ack.v0.1") &&
        equals(ack,"device_id",device) && equals(ack,"event_id",id) &&
        equals(ack,"payload_sha256",hash) && equals(ack,"status","accepted") &&
        cJSON_IsString(ack_id) && safe_id(ack_id->valuestring) && cJSON_IsNumber(time) &&
        time->valuedouble>=0 && time->valuedouble<=9007199254740991.0 && floor(time->valuedouble)==time->valuedouble;
    cJSON_Delete(root); return ok;
}
