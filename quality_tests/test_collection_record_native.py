"""Real C EGLK writer / strict durable ACK parser, using cJSON and SHA256."""
import json
from pathlib import Path
import tempfile
import unittest
from quality_tests.native_convergence import IDF, run_c

HARNESS = r'''
#include "collection_record.h"
#include "mbedtls/sha256.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void){
 char frame[4000],id[129],sha[65];unsigned char hash[32];
 cJSON *o=cJSON_Parse("{\"observation_id\":\"col-b1-imu-1\",\"sequence_id\":1,\"payload\":{\"raw\":\"ERROR\\r\\n\"}}");
 size_t length=collection_record_frame(o,frame,sizeof(frame));CHECK(length);
 CHECK(collection_record_identity(frame,length,id,sizeof(id))&&!strcmp(id,"col-b1-imu-1"));
 CHECK(strstr(frame,"content-type=application/json;profile=egolink.collection.v1\n\n"));
 CHECK(collection_record_frame(o,frame,16)==0);
 length=collection_record_frame(o,frame,sizeof(frame));CHECK(mbedtls_sha256((unsigned char*)frame,length,hash,0)==0);
 for(unsigned i=0;i<32;i++)snprintf(sha+2*i,3,"%02x",hash[i]);
 char response[2048],bad[2048];
 snprintf(response,sizeof(response),"{\"ok\":true,\"delivery_ack\":{\"contract_version\":\"egolink.persistent_priority_outbox.ack.v0.1\",\"ack_id\":\"ack-1\",\"device_id\":\"d1\",\"event_id\":\"col-b1-imu-1\",\"payload_sha256\":\"%s\",\"status\":\"accepted\",\"ack_time_ms\":1788650000000}}",sha);
 CHECK(collection_record_ack_matches(frame,length,"d1",response,strlen(response)));
 CHECK(!collection_record_ack_matches(frame,length,"d2",response,strlen(response)));
 CHECK(!collection_record_ack_matches(frame,length-1,"d1",response,strlen(response)));
 for(size_t i=0;i<strlen(response);i++)CHECK(!collection_record_ack_matches(frame,length,"d1",response,i));
 snprintf(bad,sizeof(bad),"%s{}",response);CHECK(!collection_record_ack_matches(frame,length,"d1",bad,strlen(bad)));
 cJSON *r=cJSON_Parse(response),*a=cJSON_GetObjectItem(r,"delivery_ack");
 cJSON_AddStringToObject(a,"event_id","other");char *b=cJSON_PrintUnformatted(r);
 CHECK(!collection_record_ack_matches(frame,length,"d1",b,strlen(b)));cJSON_free(b);cJSON_Delete(r);
 r=cJSON_Parse(response);a=cJSON_GetObjectItem(r,"delivery_ack");
 cJSON_ReplaceItemInObject(a,"status",cJSON_CreateString("rejected"));b=cJSON_PrintUnformatted(r);
 CHECK(!collection_record_ack_matches(frame,length,"d1",b,strlen(b)));cJSON_free(b);cJSON_Delete(r);
 CHECK(!collection_record_ack_matches(frame,length,"d1","{\"ok\":true}",11));
 cJSON_Delete(o);puts("{\"frame_and_exact_ack\":true,\"all_truncations_rejected\":true}");return 0;
}
'''

class CollectionRecordNativeTests(unittest.TestCase):
    def test_real_frame_and_ack_identity_complete_body(self):
        output = run_c(HARNESS, ["collection_record"], extra_sources=[
            IDF / "components/json/cJSON/cJSON.c",
            IDF / "components/mbedtls/mbedtls/library/sha256.c",
            IDF / "components/mbedtls/mbedtls/library/platform_util.c",
        ])
        self.assertTrue(json.loads(output)["all_truncations_rejected"])

    def test_firmware_frame_server_commit_and_firmware_ack_interoperate(self):
        from quality_tests.test_collection_ingest import envelope, raw_record, DEVICE
        from server.message_hub import MessageHubStore
        value = envelope(payload={"at": [{"command": "AT+CGNSSINFO", "response": "\r\n+CGNSSINFO:,,,,,,,,\r\nOK\r\n", "outcome": 0, "elapsed_ms": 14}], "no_fix": True})
        sources = [IDF / "components/json/cJSON/cJSON.c", IDF / "components/mbedtls/mbedtls/library/sha256.c", IDF / "components/mbedtls/mbedtls/library/platform_util.c"]
        writer = '#include "collection_record.h"\n#include <stdio.h>\nint main(void){char f[4000];cJSON *o=cJSON_Parse(' + json.dumps(json.dumps(value, separators=(",", ":"))) + ');size_t n=collection_record_frame(o,f,sizeof(f));if(!n)return 1;fwrite(f,1,n,stdout);cJSON_Delete(o);return 0;}'
        frame = run_c(writer, ["collection_record"], extra_sources=sources).encode()
        with tempfile.TemporaryDirectory() as directory:
            hub = MessageHubStore(Path(directory) / "hub.db")
            ack = hub.collection.ingest(frame, raw_record(frame), transport="wifi")
            self.assertEqual(hub.collection.ingest(frame, raw_record(frame), transport="lte")["delivery_ack"]["payload_sha256"], ack["delivery_ack"]["payload_sha256"])
        reader = '#include "collection_record.h"\n#include <string.h>\nint main(void){const char *f=' + json.dumps(frame.decode()) + ';const char *a=' + json.dumps(json.dumps(ack)) + ';return collection_record_ack_matches(f,strlen(f),' + json.dumps(DEVICE) + ',a,strlen(a))?0:1;}'
        run_c(reader, ["collection_record"], extra_sources=sources)
