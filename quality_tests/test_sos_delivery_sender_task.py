"""SOS-010K fixed-memory sender ownership and native concurrency evidence."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "firmware" / "mqtt_heartbeat" / "components"
    / "sos_delivery_sender_task"
)
SOURCE = COMPONENT / "sos_delivery_sender_task.c"
HEADER = COMPONENT / "include" / "sos_delivery_sender_task.h"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"


FREERTOS_H = r'''
#pragma once
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
typedef int BaseType_t;
typedef unsigned int UBaseType_t;
typedef uint32_t TickType_t;
typedef uint32_t configSTACK_DEPTH_TYPE;
typedef uint8_t StackType_t;
typedef void (*TaskFunction_t)(void *);
typedef struct FakeTask {
    pthread_t thread;
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    uint32_t notifications;
    TaskFunction_t entry;
    void *argument;
    atomic_bool deleted;
} StaticTask_t;
typedef StaticTask_t *TaskHandle_t;
#define pdTRUE 1
#define configMAX_PRIORITIES 16
#define configTICK_RATE_HZ 100U
#define portMAX_DELAY 1000U
#define pdMS_TO_TICKS(value) ((TickType_t)(value))
'''

TASK_H = r'''
#pragma once
#include "freertos/FreeRTOS.h"
TaskHandle_t xTaskCreateStatic(TaskFunction_t entry, const char *name,
    configSTACK_DEPTH_TYPE stack_bytes, void *argument,
    UBaseType_t priority, StackType_t *stack, StaticTask_t *buffer);
BaseType_t xTaskNotifyGive(TaskHandle_t task);
uint32_t ulTaskNotifyTake(BaseType_t clear_on_exit, TickType_t timeout_ticks);
void vTaskDelay(TickType_t ticks);
void vTaskDelete(TaskHandle_t task);
'''

TARGET_FREERTOS_H = r'''
#pragma once
#include <stdint.h>
typedef int BaseType_t;
typedef unsigned int UBaseType_t;
typedef uint32_t TickType_t;
typedef uint32_t configSTACK_DEPTH_TYPE;
typedef uint8_t StackType_t;
typedef void (*TaskFunction_t)(void *);
typedef struct { uint8_t opaque[256]; } StaticTask_t;
typedef void *TaskHandle_t;
#define pdTRUE 1
#define configMAX_PRIORITIES 16
#define configTICK_RATE_HZ 1000U
#define portMAX_DELAY UINT32_MAX
#define pdMS_TO_TICKS(value) ((TickType_t)(value))
'''

COMPOSITION_H = r'''
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef enum {
 EGOLINK_SOS_DELIVERY_COMPOSITION_OK=0,
 EGOLINK_SOS_DELIVERY_COMPOSITION_NO_EDGE,
 EGOLINK_SOS_DELIVERY_COMPOSITION_PARTIAL_FAILURE,
 EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_NO_PENDING_EDGE,
 EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD,
 EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_ALREADY_APPLIED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS,
 EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS,
 EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS,
 EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT,
 EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_CONFIG,
 EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH,
 EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_ALREADY_INITIALIZED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL,
 EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED,
 EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY,
} egolink_sos_delivery_composition_status_t;
typedef struct FakeComposition egolink_sos_delivery_composition_t;
typedef struct { int unused; } egolink_sos_delivery_composition_drive_result_t;
typedef struct { int unused; } egolink_sos_delivery_composition_shutdown_result_t;
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_prepare(egolink_sos_delivery_composition_t *,
    uint64_t, egolink_sos_delivery_composition_drive_result_t *);
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_execute_prepared(
    egolink_sos_delivery_composition_t *,
    egolink_sos_delivery_composition_drive_result_t *);
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_settle_prepared(
    egolink_sos_delivery_composition_t *, uint64_t,
    egolink_sos_delivery_composition_drive_result_t *);
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_recover_delivery_once(
    egolink_sos_delivery_composition_t *, uint64_t,
    egolink_sos_delivery_composition_drive_result_t *);
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_cancel(egolink_sos_delivery_composition_t *,
    uint64_t, egolink_sos_delivery_composition_shutdown_result_t *);
'''

HARNESS = r'''
#include "sos_delivery_sender_task.h"
#include "freertos/task.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

enum work_kind { WORK_NONE=0, WORK_LOCATION, WORK_SOS };
enum result_kind { RESULT_CANCELLED=0, RESULT_EXACT_ACK, RESULT_BAD_ACK };
enum barrier_kind { BARRIER_NONE=0, BARRIER_EXECUTE, BARRIER_RESULT_READY,
                    BARRIER_PREPARE, BARRIER_RECOVERY };
enum recovery_kind { RECOVERY_NONE=0, RECOVERY_BEGIN, RECOVERY_FINISH };

typedef struct {
 pthread_mutex_t mutex;
 atomic_bool held;
 atomic_uint attempts;
 atomic_uint enters;
 atomic_uint leaves;
 atomic_uint input_acquired;
 atomic_uint last_timeout_ms;
} owner_t;

struct FakeComposition {
 pthread_mutex_t mutex;
 pthread_cond_t condition;
 owner_t *owner;
 enum work_kind due;
 enum work_kind prepared;
 enum result_kind result;
 enum barrier_kind barrier;
 bool barrier_entered;
 bool barrier_release;
 bool sos_pending;
 atomic_bool cancel_requested;
 bool stop_cancelled;
 enum recovery_kind recovery_kind;
 bool recovery_finished;
 bool repeat_due;
 atomic_uint prepare_calls;
 atomic_uint execute_calls;
 atomic_uint settle_calls;
 atomic_uint recovery_calls;
 atomic_uint begin_recovery_calls;
 atomic_uint finish_recovery_calls;
 atomic_uint cancel_calls;
 atomic_uint exact_location_deletes;
 atomic_uint exact_sos_deletes;
 atomic_uint retained;
 atomic_uint execute_saw_owner;
};

static _Thread_local StaticTask_t *current_task;
static TaskHandle_t last_created_task;
static pthread_mutex_t public_notify_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t public_notify_condition=PTHREAD_COND_INITIALIZER;
static atomic_bool block_public_notify_return=ATOMIC_VAR_INIT(false);
static unsigned public_notify_inside;
static bool release_public_notify;

static void add_ms(struct timespec *value, uint32_t ms)
{
 value->tv_sec += (time_t)(ms / 1000U);
 value->tv_nsec += (long)(ms % 1000U) * 1000000L;
 if (value->tv_nsec >= 1000000000L) {
  ++value->tv_sec; value->tv_nsec -= 1000000000L;
 }
}

static void *task_trampoline(void *argument)
{
 StaticTask_t *task=(StaticTask_t *)argument;
 current_task=task; task->entry(task->argument); return NULL;
}

TaskHandle_t xTaskCreateStatic(TaskFunction_t entry, const char *name,
 configSTACK_DEPTH_TYPE stack_bytes, void *argument, UBaseType_t priority,
 StackType_t *stack, StaticTask_t *buffer)
{
 (void)name; (void)priority; assert(stack_bytes==6144U); assert(stack!=NULL);
 memset(buffer,0,sizeof(*buffer)); buffer->entry=entry; buffer->argument=argument;
 atomic_init(&buffer->deleted,false);
 assert(!pthread_mutex_init(&buffer->mutex,NULL));
 assert(!pthread_cond_init(&buffer->condition,NULL));
 if(pthread_create(&buffer->thread,NULL,task_trampoline,buffer)!=0) return NULL;
 last_created_task=buffer; return buffer;
}

BaseType_t xTaskNotifyGive(TaskHandle_t task)
{
 assert(task!=NULL); assert(!atomic_load(&task->deleted));
 assert(!pthread_mutex_lock(&task->mutex));
 if (task->notifications!=UINT32_MAX) ++task->notifications;
 assert(!pthread_cond_signal(&task->condition));
 assert(!pthread_mutex_unlock(&task->mutex));
 if(current_task==NULL && atomic_load(&block_public_notify_return)) {
  assert(!pthread_mutex_lock(&public_notify_mutex));
  ++public_notify_inside;
  assert(!pthread_cond_broadcast(&public_notify_condition));
  while(!release_public_notify)
   assert(!pthread_cond_wait(&public_notify_condition,&public_notify_mutex));
  assert(!pthread_mutex_unlock(&public_notify_mutex));
 }
 return 1;
}

uint32_t ulTaskNotifyTake(BaseType_t clear_on_exit, TickType_t timeout_ticks)
{
 assert(timeout_ticks>0U && timeout_ticks<portMAX_DELAY);
 assert(current_task!=NULL); assert(!pthread_mutex_lock(&current_task->mutex));
 struct timespec deadline; assert(!clock_gettime(CLOCK_REALTIME,&deadline));
 add_ms(&deadline,timeout_ticks);
 while(current_task->notifications==0U) {
  int status=pthread_cond_timedwait(&current_task->condition,
      &current_task->mutex,&deadline);
  if(status==ETIMEDOUT) break;
  assert(status==0);
 }
 uint32_t result=current_task->notifications;
 if(result!=0U) {
  if(clear_on_exit) current_task->notifications=0U;
  else --current_task->notifications;
 }
 assert(!pthread_mutex_unlock(&current_task->mutex)); return result;
}

void vTaskDelay(TickType_t ticks)
{
 assert(ticks>0U && ticks<portMAX_DELAY);
 struct timespec pause={0,1000000L};
 assert(nanosleep(&pause,NULL)==0);
}

void vTaskDelete(TaskHandle_t task)
{
 assert(task==NULL); assert(current_task!=NULL);
 atomic_store(&current_task->deleted,true);
}

static void join_sender_thread(void)
{
 assert(last_created_task!=NULL);
 assert(!pthread_join(last_created_task->thread,NULL));
 assert(atomic_load(&last_created_task->deleted));
 last_created_task=NULL;
}

static void arm_public_notify_barrier(void)
{
 assert(!pthread_mutex_lock(&public_notify_mutex));
 public_notify_inside=false; release_public_notify=false;
 atomic_store(&block_public_notify_return,true);
 assert(!pthread_mutex_unlock(&public_notify_mutex));
}

static void wait_public_notify_barrier(unsigned expected)
{
 assert(!pthread_mutex_lock(&public_notify_mutex));
 struct timespec deadline; assert(!clock_gettime(CLOCK_REALTIME,&deadline));
 add_ms(&deadline,2000U);
 while(public_notify_inside<expected) {
  int status=pthread_cond_timedwait(&public_notify_condition,
      &public_notify_mutex,&deadline);
  assert(status==0);
 }
 assert(!pthread_mutex_unlock(&public_notify_mutex));
}

static void release_public_notify_barrier(void)
{
 assert(!pthread_mutex_lock(&public_notify_mutex));
 release_public_notify=true;
 atomic_store(&block_public_notify_return,false);
 assert(!pthread_cond_broadcast(&public_notify_condition));
 assert(!pthread_mutex_unlock(&public_notify_mutex));
}

static uint64_t now_ms(void *context)
{
 (void)context; struct timespec value; assert(!clock_gettime(CLOCK_MONOTONIC,&value));
 return (uint64_t)value.tv_sec*1000U+(uint64_t)value.tv_nsec/1000000U;
}

static bool owner_enter(void *context, uint32_t timeout_ms)
{
 owner_t *owner=(owner_t *)context; uint64_t deadline=now_ms(NULL)+timeout_ms;
 atomic_fetch_add(&owner->attempts,1U);
 atomic_store(&owner->last_timeout_ms,timeout_ms);
 do {
  if(pthread_mutex_trylock(&owner->mutex)==0) {
   assert(!atomic_exchange(&owner->held,true));
   atomic_fetch_add(&owner->enters,1U); return true;
  }
  struct timespec pause={0,1000000L}; nanosleep(&pause,NULL);
 } while(now_ms(NULL)<deadline);
 return false;
}

static void owner_leave(void *context)
{
 owner_t *owner=(owner_t *)context;
 assert(atomic_exchange(&owner->held,false)); atomic_fetch_add(&owner->leaves,1U);
 assert(!pthread_mutex_unlock(&owner->mutex));
}

static void barrier_wait(struct FakeComposition *composition,
                         enum barrier_kind barrier)
{
 assert(!pthread_mutex_lock(&composition->mutex));
 if(composition->barrier==barrier) {
  composition->barrier_entered=true;
  assert(!pthread_cond_broadcast(&composition->condition));
  while(!composition->barrier_release)
   assert(!pthread_cond_wait(&composition->condition,&composition->mutex));
 }
 assert(!pthread_mutex_unlock(&composition->mutex));
}

static void wait_barrier(struct FakeComposition *composition)
{
 assert(!pthread_mutex_lock(&composition->mutex));
 struct timespec deadline; assert(!clock_gettime(CLOCK_REALTIME,&deadline));
 add_ms(&deadline,2000U);
 while(!composition->barrier_entered) {
  int status=pthread_cond_timedwait(&composition->condition,
      &composition->mutex,&deadline);
  assert(status==0);
 }
 assert(!pthread_mutex_unlock(&composition->mutex));
}

static void release_barrier(struct FakeComposition *composition)
{
 assert(!pthread_mutex_lock(&composition->mutex));
 composition->barrier_release=true;
 assert(!pthread_cond_broadcast(&composition->condition));
 assert(!pthread_mutex_unlock(&composition->mutex));
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_prepare(struct FakeComposition *composition,
 uint64_t now, egolink_sos_delivery_composition_drive_result_t *result)
{
 (void)now; (void)result; assert(atomic_load(&composition->owner->held));
 atomic_fetch_add(&composition->prepare_calls,1U);
 if(composition->recovery_kind!=RECOVERY_NONE && !composition->recovery_finished)
  return EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
 if(composition->sos_pending) { composition->prepared=WORK_SOS;
  composition->sos_pending=false; composition->result=RESULT_EXACT_ACK; }
 else composition->prepared=composition->due;
 if(composition->prepared==WORK_NONE)
  return EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD;
 barrier_wait(composition,BARRIER_PREPARE);
 return EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_execute_prepared(struct FakeComposition *composition,
 egolink_sos_delivery_composition_drive_result_t *result)
{
 (void)result; atomic_fetch_add(&composition->execute_calls,1U);
 if(atomic_load(&composition->owner->held))
  atomic_fetch_add(&composition->execute_saw_owner,1U);
 barrier_wait(composition,BARRIER_EXECUTE);
 if(atomic_load(&composition->cancel_requested) &&
    composition->prepared==WORK_LOCATION)
  composition->result=RESULT_CANCELLED;
 barrier_wait(composition,BARRIER_RESULT_READY);
 return EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_settle_prepared(struct FakeComposition *composition,
 uint64_t now, egolink_sos_delivery_composition_drive_result_t *result)
{
 (void)now; (void)result; assert(atomic_load(&composition->owner->held));
 atomic_fetch_add(&composition->settle_calls,1U);
 if(composition->result==RESULT_EXACT_ACK) {
  if(composition->prepared==WORK_LOCATION)
   atomic_fetch_add(&composition->exact_location_deletes,1U);
  else atomic_fetch_add(&composition->exact_sos_deletes,1U);
 } else atomic_fetch_add(&composition->retained,1U);
 if(!composition->repeat_due) composition->due=WORK_NONE;
 composition->prepared=WORK_NONE;
 return composition->result==RESULT_EXACT_ACK
  ? EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED
  : EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_recover_delivery_once(
 struct FakeComposition *composition, uint64_t now,
 egolink_sos_delivery_composition_drive_result_t *result)
{
 (void)now; (void)result; assert(atomic_load(&composition->owner->held));
 atomic_fetch_add(&composition->recovery_calls,1U);
 if(composition->recovery_kind==RECOVERY_BEGIN)
  atomic_fetch_add(&composition->begin_recovery_calls,1U);
 else if(composition->recovery_kind==RECOVERY_FINISH)
  atomic_fetch_add(&composition->finish_recovery_calls,1U);
 barrier_wait(composition,BARRIER_RECOVERY);
 composition->recovery_finished=true;
 return EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_cancel(struct FakeComposition *composition,
 uint64_t now, egolink_sos_delivery_composition_shutdown_result_t *result)
{
 (void)now; (void)result; assert(atomic_load(&composition->owner->held));
 atomic_fetch_add(&composition->cancel_calls,1U);
 composition->stop_cancelled=true;
 return EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
}

static void initialize_owner(owner_t *owner)
{
 memset(owner,0,sizeof(*owner)); assert(!pthread_mutex_init(&owner->mutex,NULL));
 atomic_init(&owner->held,false); atomic_init(&owner->attempts,0U);
 atomic_init(&owner->enters,0U);
 atomic_init(&owner->leaves,0U); atomic_init(&owner->input_acquired,0U);
 atomic_init(&owner->last_timeout_ms,0U);
}

static void initialize_composition(struct FakeComposition *composition,
 owner_t *owner, enum work_kind work, enum result_kind result,
 enum barrier_kind barrier)
{
 memset(composition,0,sizeof(*composition));
 assert(!pthread_mutex_init(&composition->mutex,NULL));
 assert(!pthread_cond_init(&composition->condition,NULL));
 composition->owner=owner; composition->due=work; composition->result=result;
 composition->barrier=barrier;
 atomic_init(&composition->cancel_requested,false);
}

static void initialize_sender_with_limits(
 egolink_sos_delivery_sender_task_t *sender,
 struct FakeComposition *composition, owner_t *owner,
 uint32_t owner_timeout_ms, uint32_t idle_poll_ms, uint32_t stop_timeout_ms)
{
 memset(sender,0,sizeof(*sender));
 egolink_sos_delivery_sender_task_config_t config;
 egolink_sos_delivery_sender_task_default_config(&config);
 config.enabled=true; config.composition=composition;
 config.owner_enter=owner_enter; config.owner_leave=owner_leave;
 config.owner_context=owner; config.now_ms=now_ms;
 config.owner_timeout_ms=owner_timeout_ms; config.idle_poll_ms=idle_poll_ms;
 config.stop_timeout_ms=stop_timeout_ms; config.start_with_pending_work=true;
 assert(egolink_sos_delivery_sender_task_init(sender,&config)==
        EGOLINK_SOS_SENDER_TASK_OK);
}

static void initialize_sender(egolink_sos_delivery_sender_task_t *sender,
 struct FakeComposition *composition, owner_t *owner)
{
 initialize_sender_with_limits(sender,composition,owner,20U,10U,1000U);
}

static egolink_sos_delivery_sender_task_snapshot_t wait_for(
 egolink_sos_delivery_sender_task_t *sender,
 bool (*predicate)(const egolink_sos_delivery_sender_task_snapshot_t *))
{
 uint64_t deadline=now_ms(NULL)+3000U;
 egolink_sos_delivery_sender_task_snapshot_t snapshot;
 do {
  (void)egolink_sos_delivery_sender_task_current_status(sender,&snapshot);
  if(predicate(&snapshot)) return snapshot;
  struct timespec pause={0,1000000L}; nanosleep(&pause,NULL);
 } while(now_ms(NULL)<deadline);
 assert(!"sender wait timed out"); return snapshot;
}

static bool exited(const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->terminal_committed; }
static bool two_settled(const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->settle_calls>=2U; }

static void stop_and_wait(egolink_sos_delivery_sender_task_t *sender)
{
 assert(egolink_sos_delivery_sender_task_request_stop(sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(snapshot.no_direct_outbox_or_journal_api);
 join_sender_thread();
}

typedef struct {
 egolink_sos_delivery_sender_task_t *sender;
 uint32_t generations[25];
} storm_argument_t;

static void *notify_storm(void *opaque)
{
 storm_argument_t *argument=(storm_argument_t *)opaque;
 for(unsigned index=0U;index<25U;++index)
  assert(egolink_sos_delivery_sender_task_notify(
      argument->sender,&argument->generations[index])==
      EGOLINK_SOS_SENDER_TASK_OK);
 return NULL;
}

static bool stale_wake_seen(
 const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->stale_wake_generations_rejected>=1U; }

static void cancel_wins_and_wake_storm(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_EXACT_ACK,
                        BARRIER_EXECUTE);
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);

 /* A blocked Location POST is outside the owner. The complete physical-input
  * safety fan-out can therefore acquire the same owner and finish. */
 assert(owner_enter(&owner,20U)); atomic_fetch_add(&owner.input_acquired,1U);
 atomic_store(&composition.cancel_requested,true); composition.sos_pending=true;
 unsigned feedback=1U,journal=1U,location=1U,call=1U;
 owner_leave(&owner);
 pthread_t storm_threads[4]; storm_argument_t storm[4];
 memset(storm,0,sizeof(storm));
 for(unsigned index=0U;index<4U;++index) {
  storm[index].sender=&sender;
  assert(!pthread_create(&storm_threads[index],NULL,notify_storm,&storm[index]));
 }
 for(unsigned index=0U;index<4U;++index)
  assert(!pthread_join(storm_threads[index],NULL));
 bool generations_seen[102]={false};
 for(unsigned thread=0U;thread<4U;++thread)
  for(unsigned index=0U;index<25U;++index) {
   uint32_t generation=storm[thread].generations[index];
   assert(generation>=2U && generation<=101U);
   assert(!generations_seen[generation]); generations_seen[generation]=true;
  }
 release_barrier(&composition);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,two_settled);
 assert(feedback==1U && journal==1U && location==1U && call==1U);
 assert(atomic_load(&owner.input_acquired)==1U);
 assert(atomic_load(&composition.execute_saw_owner)==0U);
 assert(atomic_load(&composition.retained)==1U);
 assert(atomic_load(&composition.exact_location_deletes)==0U);
 assert(atomic_load(&composition.exact_sos_deletes)==1U);
 assert(snapshot.coalesced_notifications>0U);
 assert(snapshot.notifications==100U);
 assert(snapshot.wake_generation==101U);
 assert(snapshot.last_attempt_generation>=2U);
 assert(snapshot.active_attempt_generation==0U);
 /* A delayed/duplicated RTOS notification carries no new generation and
  * cannot create a send or settle another result. */
 assert(xTaskNotifyGive(last_created_task)==1);
 snapshot=wait_for(&sender,stale_wake_seen);
 assert(snapshot.settle_calls==2U);
 assert(atomic_load(&composition.retained)==1U);
 assert(atomic_load(&composition.exact_sos_deletes)==1U);
 stop_and_wait(&sender);
}

static bool one_settled(const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->settle_calls>=1U; }

static void non_exact_ack_is_retained(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_BAD_ACK,
                        BARRIER_NONE);
 initialize_sender(&sender,&composition,&owner);
 (void)wait_for(&sender,one_settled);
 assert(atomic_load(&composition.retained)==1U);
 assert(atomic_load(&composition.exact_location_deletes)==0U);
 assert(atomic_load(&composition.exact_sos_deletes)==0U);
 stop_and_wait(&sender);
}

static void result_wins_before_late_cancel(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_EXACT_ACK,
                        BARRIER_RESULT_READY);
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
 /* Hold owner while allowing an already-produced result to return. A later
  * SOS cancellation cannot rewrite that exact transport result. */
 assert(owner_enter(&owner,20U)); release_barrier(&composition);
 atomic_store(&composition.cancel_requested,true); composition.sos_pending=true;
 owner_leave(&owner);
 (void)wait_for(&sender,two_settled);
 assert(atomic_load(&composition.exact_location_deletes)==1U);
 assert(atomic_load(&composition.exact_sos_deletes)==1U);
 stop_and_wait(&sender);
}

static bool preparing(const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->phase==EGOLINK_SOS_SENDER_TASK_PHASE_PREPARING; }

static void shutdown_prepared_never_executes(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_EXACT_ACK,
                        BARRIER_PREPARE);
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
 (void)wait_for(&sender,preparing);
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 release_barrier(&composition);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(atomic_load(&composition.execute_calls)==0U);
 assert(atomic_load(&composition.cancel_calls)==1U);
 join_sender_thread();
}

static void shutdown_executing_settles_before_cancel(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_BAD_ACK,
                        BARRIER_EXECUTE);
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 release_barrier(&composition);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(atomic_load(&composition.settle_calls)==1U);
 assert(atomic_load(&composition.retained)==1U);
 assert(atomic_load(&composition.cancel_calls)==1U);
 join_sender_thread();
}

static void stop_during_execute_uses_one_budgeted_settle_attempt(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_BAD_ACK,
                        BARRIER_EXECUTE);
 initialize_sender_with_limits(&sender,&composition,&owner,30U,1U,30U);
 wait_barrier(&composition);
 /* Deny settlement after execute. The stop arriving inside execute must
  * establish its deadline before any owner wait: exactly one remaining-budget
  * attempt, not one ordinary 30 ms wait followed by a second stop wait. */
 assert(owner_enter(&owner,20U));
 unsigned owner_attempts=atomic_load(&owner.attempts);
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 release_barrier(&composition);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(snapshot.owner_timeouts==1U);
 assert(atomic_load(&owner.attempts)==owner_attempts+1U);
 assert(atomic_load(&owner.last_timeout_ms)>0U);
 assert(atomic_load(&owner.last_timeout_ms)<=30U);
 assert(atomic_load(&composition.settle_calls)==0U);
 assert(atomic_load(&composition.cancel_calls)==0U);
 owner_leave(&owner); join_sender_thread();
}

static bool result_ready_phase(
 const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->phase==EGOLINK_SOS_SENDER_TASK_PHASE_RESULT_READY; }

static void shutdown_result_ready_settles_before_cancel(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_BAD_ACK,
                        BARRIER_RESULT_READY);
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
 /* Keep settlement's owner unavailable after execute has captured its result,
  * making RESULT_READY externally observable without racing result bytes. */
 assert(owner_enter(&owner,20U)); release_barrier(&composition);
 (void)wait_for(&sender,result_ready_phase);
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 assert(atomic_load(&composition.cancel_calls)==0U);
 owner_leave(&owner);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(atomic_load(&composition.settle_calls)==1U);
 assert(atomic_load(&composition.retained)==1U);
 assert(atomic_load(&composition.cancel_calls)==1U);
 join_sender_thread();
}

static void shutdown_recovery_matrix(void)
{
 for(unsigned pass=0;pass<2U;++pass) {
  owner_t owner; struct FakeComposition composition;
  egolink_sos_delivery_sender_task_t sender;
  initialize_owner(&owner);
  initialize_composition(&composition,&owner,WORK_NONE,RESULT_BAD_ACK,
                          BARRIER_RECOVERY);
  composition.recovery_kind=pass==0U?RECOVERY_BEGIN:RECOVERY_FINISH;
  initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
  assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
         EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
  release_barrier(&composition);
  egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
  assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
  assert(atomic_load(&composition.recovery_calls)==1U);
  assert(atomic_load(&composition.begin_recovery_calls)==(pass==0U?1U:0U));
  assert(atomic_load(&composition.finish_recovery_calls)==(pass==1U?1U:0U));
  assert(atomic_load(&composition.cancel_calls)==1U);
  join_sender_thread();
 }
}

static bool prepared_at_least_once(
 const egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{ return snapshot->prepare_calls>=1U; }

static void shutdown_owner_timeout_fails_closed(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_NONE,RESULT_BAD_ACK,
                        BARRIER_NONE);
 initialize_sender_with_limits(&sender,&composition,&owner,5U,5U,30U);
 (void)wait_for(&sender,prepared_at_least_once);
 assert(owner_enter(&owner,20U));
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(snapshot.last_status==EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
 assert(snapshot.owner_timeouts>=1U);
 assert(atomic_load(&composition.cancel_calls)==0U);
 owner_leave(&owner); join_sender_thread();
}

static void generation_exhaustion_is_terminal(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_EXACT_ACK,
                        BARRIER_NONE);
 composition.repeat_due=true;
 initialize_sender(&sender,&composition,&owner);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(snapshot.last_status==EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED);
 assert(snapshot.last_attempt_generation==3U);
 assert(snapshot.prepare_calls==3U && snapshot.execute_calls==3U);
 assert(snapshot.settle_calls==3U);
 unsigned enters=atomic_load(&owner.enters),leaves=atomic_load(&owner.leaves);
 assert(enters==leaves);
 join_sender_thread();
 assert(atomic_load(&owner.enters)==enters);
 assert(atomic_load(&owner.leaves)==leaves);
}

typedef struct {
 egolink_sos_delivery_sender_task_t *sender;
 egolink_sos_delivery_sender_task_status_t status;
} public_call_argument_t;

static void *notify_once(void *opaque)
{
 public_call_argument_t *argument=(public_call_argument_t *)opaque;
 argument->status=egolink_sos_delivery_sender_task_notify(
     argument->sender,NULL);
 return NULL;
}

static void *request_stop_once(void *opaque)
{
 public_call_argument_t *argument=(public_call_argument_t *)opaque;
 argument->status=egolink_sos_delivery_sender_task_request_stop(
     argument->sender);
 return NULL;
}

static void terminal_waits_for_inflight_notify(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_LOCATION,RESULT_EXACT_ACK,
                        BARRIER_EXECUTE);
 composition.repeat_due=true;
 initialize_sender(&sender,&composition,&owner); wait_barrier(&composition);
 arm_public_notify_barrier();
 public_call_argument_t argument={&sender,EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT};
 pthread_t caller; assert(!pthread_create(&caller,NULL,notify_once,&argument));
 wait_public_notify_barrier(1U);
 release_barrier(&composition);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(snapshot.last_status==EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED);
 assert(snapshot.public_calls_in_flight==1U);
 assert(!atomic_load(&last_created_task->deleted));
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
 assert(egolink_sos_delivery_sender_task_notify(&sender,NULL)==
        EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
 egolink_sos_delivery_sender_task_snapshot_t closed;
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&closed);
 assert(closed.public_calls_in_flight==1U);
 assert(closed.last_status==EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED);
 unsigned enters=atomic_load(&owner.enters),leaves=atomic_load(&owner.leaves);
 release_public_notify_barrier();
 assert(!pthread_join(caller,NULL));
 assert(argument.status==EGOLINK_SOS_SENDER_TASK_OK);
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&closed);
 assert(closed.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(closed.last_status==EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED);
 assert(closed.public_calls_in_flight==0U);
 join_sender_thread();
 assert(atomic_load(&owner.enters)==enters);
 assert(atomic_load(&owner.leaves)==leaves);
}

static void terminal_waits_for_inflight_stop(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_NONE,RESULT_BAD_ACK,
                        BARRIER_NONE);
 initialize_sender(&sender,&composition,&owner);
 (void)wait_for(&sender,prepared_at_least_once);
 arm_public_notify_barrier();
 public_call_argument_t argument={&sender,EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT};
 pthread_t caller;
 assert(!pthread_create(&caller,NULL,request_stop_once,&argument));
 wait_public_notify_barrier(1U);
 egolink_sos_delivery_sender_task_snapshot_t snapshot=wait_for(&sender,exited);
 assert(snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(snapshot.public_calls_in_flight==1U);
 assert(atomic_load(&composition.cancel_calls)==1U);
 assert(!atomic_load(&last_created_task->deleted));
 assert(egolink_sos_delivery_sender_task_request_stop(&sender)==
        EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS);
 assert(egolink_sos_delivery_sender_task_notify(&sender,NULL)==
        EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS);
 egolink_sos_delivery_sender_task_snapshot_t closed;
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&closed);
 assert(closed.public_calls_in_flight==1U);
 release_public_notify_barrier();
 assert(!pthread_join(caller,NULL));
 assert(argument.status==EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&closed);
 assert(closed.lifecycle==EGOLINK_SOS_SENDER_TASK_STOPPED);
 assert(closed.last_status==EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS);
 assert(closed.public_calls_in_flight==0U);
 join_sender_thread();
}

static void public_call_limit_never_wraps_or_notifies(void)
{
 owner_t owner; struct FakeComposition composition;
 egolink_sos_delivery_sender_task_t sender;
 initialize_owner(&owner);
 initialize_composition(&composition,&owner,WORK_NONE,RESULT_BAD_ACK,
                        BARRIER_NONE);
 initialize_sender(&sender,&composition,&owner);
 (void)wait_for(&sender,prepared_at_least_once);
 arm_public_notify_barrier();
 public_call_argument_t arguments[4]; pthread_t callers[4];
 for(unsigned index=0U;index<4U;++index) {
  arguments[index].sender=&sender;
  arguments[index].status=EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT;
  assert(!pthread_create(&callers[index],NULL,notify_once,&arguments[index]));
 }
 wait_public_notify_barrier(4U);
 egolink_sos_delivery_sender_task_snapshot_t before;
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&before);
 assert(before.public_calls_in_flight==4U && before.notifications==4U);
 assert(egolink_sos_delivery_sender_task_notify(&sender,NULL)==
        EGOLINK_SOS_SENDER_TASK_PUBLIC_CALL_LIMIT);
 egolink_sos_delivery_sender_task_snapshot_t after;
 (void)egolink_sos_delivery_sender_task_current_status(&sender,&after);
 assert(after.public_calls_in_flight==4U);
 assert(after.notifications==before.notifications);
 assert(!atomic_load(&last_created_task->deleted));
 release_public_notify_barrier();
 for(unsigned index=0U;index<4U;++index) {
  assert(!pthread_join(callers[index],NULL));
  assert(arguments[index].status==EGOLINK_SOS_SENDER_TASK_OK);
 }
 stop_and_wait(&sender);
}

int main(void)
{
 egolink_sos_delivery_sender_task_config_t disabled;
 egolink_sos_delivery_sender_task_default_config(&disabled);
 assert(!disabled.enabled);
 owner_t invalid_owner; struct FakeComposition invalid_composition;
 egolink_sos_delivery_sender_task_t invalid_sender;
 initialize_owner(&invalid_owner);
 initialize_composition(&invalid_composition,&invalid_owner,WORK_NONE,
                        RESULT_BAD_ACK,BARRIER_NONE);
 disabled.enabled=true; disabled.composition=&invalid_composition;
 disabled.owner_enter=owner_enter; disabled.owner_leave=owner_leave;
 disabled.owner_context=&invalid_owner; disabled.now_ms=now_ms;
 disabled.owner_timeout_ms=5U; disabled.idle_poll_ms=10000U;
 disabled.stop_timeout_ms=30U; disabled.task_priority=3U;
 memset(&invalid_sender,0,sizeof(invalid_sender));
 assert(egolink_sos_delivery_sender_task_init(&invalid_sender,&disabled)==
        EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG);
 egolink_sos_delivery_sender_task_snapshot_t invalid_snapshot;
 assert(egolink_sos_delivery_sender_task_current_status(
     &invalid_sender,&invalid_snapshot)==EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG);
 assert(invalid_snapshot.lifecycle==EGOLINK_SOS_SENDER_TASK_STOP_FAILED);
 assert(invalid_snapshot.terminal_committed);
 assert(egolink_sos_delivery_sender_task_request_stop(&invalid_sender)==
        EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
 egolink_sos_delivery_sender_task_config_t owner_over_budget=disabled;
 egolink_sos_delivery_sender_task_t owner_over_budget_sender;
 owner_over_budget.idle_poll_ms=10U;
 owner_over_budget.owner_timeout_ms=31U;
 owner_over_budget.stop_timeout_ms=30U;
 memset(&owner_over_budget_sender,0,sizeof(owner_over_budget_sender));
 assert(egolink_sos_delivery_sender_task_init(
     &owner_over_budget_sender,&owner_over_budget)==
     EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG);
 assert(egolink_sos_delivery_sender_task_request_stop(
     &owner_over_budget_sender)==EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
 cancel_wins_and_wake_storm();
 non_exact_ack_is_retained();
 result_wins_before_late_cancel();
 shutdown_prepared_never_executes();
 shutdown_executing_settles_before_cancel();
 stop_during_execute_uses_one_budgeted_settle_attempt();
 shutdown_result_ready_settles_before_cancel();
 shutdown_recovery_matrix();
 shutdown_owner_timeout_fails_closed();
 generation_exhaustion_is_terminal();
 terminal_waits_for_inflight_notify();
 terminal_waits_for_inflight_stop();
 public_call_limit_never_wraps_or_notifies();
 puts("SOS sender pthread: owner split, race, generation, wake storm, shutdown PASS");
 return 0;
}
'''


def compile_and_run() -> str:
    compiler = os.environ.get("CC") or shutil.which("gcc") or str(
        ROOT / "tmp" / "native_tools" / "w64devkit" / "bin" / "gcc.exe"
    )
    if not Path(compiler).is_file():
        raise unittest.SkipTest("host GCC unavailable")
    with tempfile.TemporaryDirectory(prefix="ego-sos-sender-") as directory:
        temporary = Path(directory)
        for relative, content in {
            "sdkconfig.h": "#define CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED 1\n",
            "freertos/FreeRTOS.h": FREERTOS_H,
            "freertos/task.h": TASK_H,
            "sos_delivery_composition.h": COMPOSITION_H,
            "harness.c": HARNESS,
        }.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        executable = temporary / "sender.exe"
        command = [
            compiler, "-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror",
            "-Wconversion", "-Wformat=2", "-Wshadow", "-Wsign-conversion",
            "-DEGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX=3",
            "-DEGOLINK_SOS_SENDER_PUBLIC_CALL_MAX=4",
            f"-I{temporary}", f"-I{COMPONENT / 'include'}",
            str(SOURCE), str(temporary / "harness.c"), "-o", str(executable),
        ]
        environment = dict(os.environ)
        environment["PATH"] = str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
        built = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=60,
            env=environment,
        )
        if built.returncode:
            raise AssertionError(built.stdout + built.stderr)
        ran = subprocess.run(
            [str(executable)], cwd=ROOT, capture_output=True, text=True,
            timeout=30, env=environment,
        )
        if ran.returncode:
            raise AssertionError(
                f"native exit={ran.returncode}\n{ran.stdout}{ran.stderr}"
            )
        return ran.stdout


def build_actual_idf_component() -> str:
    """Build a temporary app that names K in REQUIRES; no tracked main edit."""
    idf = Path("C:/Espressif/v5.4.2/esp-idf")
    python = Path("C:/Espressif/tools/python/v5.4.2/venv/Scripts/python.exe")
    if not idf.is_dir() or not python.is_file():
        raise unittest.SkipTest("ESP-IDF v5.4.2 environment unavailable")
    components = ROOT / "firmware" / "mqtt_heartbeat" / "components"
    with tempfile.TemporaryDirectory(prefix="ego-sos-sender-idf-") as directory:
        project = Path(directory)
        (project / "main").mkdir()
        (project / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\n"
            f'set(EXTRA_COMPONENT_DIRS "{components.as_posix()}")\n'
            "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\n"
            "project(egolink_sos_sender_component_check)\n",
            encoding="utf-8",
        )
        (project / "main" / "CMakeLists.txt").write_text(
            'idf_component_register(SRCS "main.c" INCLUDE_DIRS "." '
            "REQUIRES sos_delivery_sender_task)\n",
            encoding="utf-8",
        )
        (project / "main" / "main.c").write_text(
            '#include "sos_delivery_sender_task.h"\n'
            "void app_main(void) {\n"
            "    egolink_sos_delivery_sender_task_config_t config;\n"
            "    egolink_sos_delivery_sender_task_default_config(&config);\n"
            "}\n",
            encoding="utf-8",
        )
        defaults = project / "sdkconfig.defaults"
        defaults.write_text(
            "CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED=y\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["IDF_PATH"] = str(idf)
        environment["IDF_TOOLS_PATH"] = "C:/Espressif/tools"
        environment["IDF_PYTHON_ENV_PATH"] = str(python.parent.parent)
        tool_paths = [
            "C:/Espressif/tools/cmake/3.30.2/bin",
            "C:/Espressif/tools/ninja/1.12.1",
            "C:/Espressif/tools/ccache/4.10.2",
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin",
            "C:/Espressif/tools/riscv32-esp-elf/esp-14.2.0_20241119/riscv32-esp-elf/bin",
            "C:/Espressif/tools/esp32ulp-elf/2.38_20240113/esp32ulp-elf/bin",
        ]
        environment["PATH"] = os.pathsep.join(tool_paths) + os.pathsep + environment.get("PATH", "")
        completed = subprocess.run(
            [
                str(python), str(idf / "tools" / "idf.py"),
                "-C", str(project), "-B", str(project / "build"),
                "-D", "IDF_TARGET=esp32s3",
                "-D", f"SDKCONFIG_DEFAULTS={defaults}", "build",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=240,
            env=environment,
        )
        if completed.returncode:
            raise AssertionError(completed.stdout + completed.stderr)
        return completed.stdout + completed.stderr


class SosDeliverySenderTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")

    def test_native_concurrent_owner_and_shutdown_contract(self) -> None:
        # Repeat complete process/thread lifecycles to catch ordering that a
        # single scheduler run can hide.
        for iteration in range(10):
            with self.subTest(iteration=iteration):
                self.assertIn("shutdown PASS", compile_and_run())

    def test_default_off_source_compiles_strictly(self) -> None:
        compiler = os.environ.get("CC") or shutil.which("gcc") or str(
            ROOT / "tmp" / "native_tools" / "w64devkit" / "bin" / "gcc.exe"
        )
        if not Path(compiler).is_file():
            self.skipTest("host GCC unavailable")
        with tempfile.TemporaryDirectory(prefix="ego-sos-sender-off-") as directory:
            temporary = Path(directory)
            for relative, content in {
                "sdkconfig.h": "#define CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED 0\n",
                "freertos/FreeRTOS.h": FREERTOS_H,
                "freertos/task.h": TASK_H,
                "sos_delivery_composition.h": COMPOSITION_H,
            }.items():
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            environment = dict(os.environ)
            environment["PATH"] = (
                str(Path(compiler).parent) + os.pathsep
                + environment.get("PATH", "")
            )
            completed = subprocess.run(
                [
                    compiler, "-std=c11", "-pthread", "-Wall", "-Wextra",
                    "-Werror", "-Wconversion", "-Wformat=2", "-Wshadow",
                    "-Wsign-conversion", f"-I{temporary}",
                    f"-I{COMPONENT / 'include'}", "-c", str(SOURCE),
                    "-o", str(temporary / "sender.o"),
                ],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
                env=environment,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

    def test_actual_source_cross_compiles_for_esp32s3(self) -> None:
        compiler = Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        )
        if not compiler.is_file():
            self.skipTest("ESP32-S3 compiler unavailable")
        components = ROOT / "firmware" / "mqtt_heartbeat" / "components"
        with tempfile.TemporaryDirectory(prefix="ego-sos-sender-xtensa-") as directory:
            temporary = Path(directory)
            for relative, content in {
                "sdkconfig.h": "#define CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED 1\n",
                "freertos/FreeRTOS.h": TARGET_FREERTOS_H,
                "freertos/task.h": TASK_H,
            }.items():
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            command = [
                str(compiler), "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Wconversion", "-Wformat=2", "-Wshadow", "-Wsign-conversion",
                f"-I{temporary}", f"-I{COMPONENT / 'include'}",
            ]
            command.extend(f"-I{path}" for path in components.glob("*/include"))
            command.extend([
                "-c", str(SOURCE), "-o", str(temporary / "sender.o"),
            ])
            completed = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

    @unittest.skipUnless(
        os.environ.get("EGOLINK_RUN_IDF_SOS_SENDER_BUILD") == "1",
        "set EGOLINK_RUN_IDF_SOS_SENDER_BUILD=1 for isolated IDF build",
    )
    def test_actual_esp_idf_component_build(self) -> None:
        output = build_actual_idf_component()
        self.assertIn("Project build complete", output)

    def test_fixed_memory_default_off_and_no_direct_storage_api(self) -> None:
        self.assertIn("default n", (COMPONENT / "Kconfig").read_text(encoding="utf-8"))
        self.assertIn("xTaskCreateStatic(", self.source)
        self.assertNotRegex(self.source, r"\bxTaskCreate\(")
        self.assertNotRegex(self.source, r"\b(?:malloc|calloc|realloc|free)\(")
        for forbidden in (
            "egolink_outbox_", "egolink_sos_pending_edge_journal_",
            "egolink_location_outbox_adapter_",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("no_direct_outbox_or_journal_api", self.header)

    def test_generation_and_owner_boundaries_are_explicit(self) -> None:
        self.assertIn("result_generation != active", self.source)
        self.assertIn("last_attempt_generation", self.source)
        execute = self.source.index(
            "egolink_sos_delivery_composition_execute_prepared("
        )
        prior_leave = self.source.rfind("leave_owner(internal);", 0, execute)
        next_enter = self.source.find("enter_owner(internal)", execute)
        self.assertGreater(prior_leave, 0)
        self.assertGreater(next_enter, execute)
        self.assertNotIn("pdMS_TO_TICKS(", self.source)
        self.assertIn("ticks = 1U", self.source)
        terminal_check = self.source.index(
            "if (atomic_load(&internal->terminal_committed))"
        )
        public_ref_drain = self.source.index(
            "atomic_load(&internal->public_call_gate)", terminal_check
        )
        task_delete = self.source.index("vTaskDelete(NULL)", terminal_check)
        self.assertLess(terminal_check, public_ref_drain)
        self.assertLess(public_ref_drain, task_delete)
        self.assertIn(
            "count >= (unsigned int)EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX",
            self.source,
        )
        self.assertNotIn(
            "atomic_fetch_add(&internal->public_call_gate", self.source
        )
        commit = self.source.index("static void commit_terminal(")
        close = self.source.index("atomic_fetch_or(", commit)
        terminal = self.source.index(
            "atomic_store(&internal->terminal_committed, true)", close
        )
        self.assertLess(close, terminal)
        request = self.source[
            self.source.index("egolink_sos_delivery_sender_task_request_stop(\n"):
            self.source.index("egolink_sos_delivery_sender_task_current_status(\n")
        ]
        self.assertIn("atomic_compare_exchange_strong", request)
        self.assertNotIn("atomic_store(&internal->lifecycle", request)
        self.assertNotIn("set_status(internal", request)
        self.assertIn("remaining_stop_owner_timeout", self.source)
        self.assertIn("stop_aware_wait_ticks", self.source)
        self.assertIn(
            "config->owner_timeout_ms > config->stop_timeout_ms", self.source
        )
        wait_start = self.source.index("static TickType_t stop_aware_wait_ticks")
        wait_end = self.source.index("static bool final_stop_status", wait_start)
        wait_source = self.source[wait_start:wait_end]
        self.assertLess(
            wait_source.index("const uint32_t wait_ms"),
            wait_source.index("bounded_wait_ticks(wait_ms"),
        )
        self.assertNotIn("bounded_wait_ticks((uint32_t)remaining_ms", wait_source)
        for signature in (
            "egolink_sos_delivery_sender_task_notify(\n    egolink",
            "egolink_sos_delivery_sender_task_request_stop(\n    egolink",
        ):
            start = self.source.index(signature)
            enter = self.source.index("enter_public_call(internal)", start)
            notify = self.source.index("xTaskNotifyGive", enter)
            leave = self.source.index("leave_public_call(internal);", notify)
            self.assertLess(enter, notify)
            self.assertLess(notify, leave)

    def test_packet_records_k_scope_and_evidence(self) -> None:
        packet = PACKET.read_text(encoding="utf-8")
        for phrase in (
            "SOS-010K", "Independent Sender", "exact ACK", "default-off",
            "physical button", "real Ego Call",
        ):
            self.assertIn(phrase, packet)


if __name__ == "__main__":
    unittest.main()
