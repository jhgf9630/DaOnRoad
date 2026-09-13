"""Bounded in-process job API. Completed personal data expires after one hour."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from api.models import RouteRequest
from solver.vrp_solver import RoutingError

router = APIRouter()
work_lock = threading.Lock()
state_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='route')
jobs = {}


class Cancelled(Exception):
    pass


def _cleanup():
    for key in list(jobs):
        if jobs[key]['status'] in ('completed', 'failed', 'cancelled') and time.time()-jobs[key]['updated_at'] > 3600:
            del jobs[key]
    completed = sorted((key for key in jobs if jobs[key]['status'] in ('completed','failed','cancelled')), key=lambda key: jobs[key]['updated_at'])
    for key in completed[:-5]:
        del jobs[key]


def _run(job_id, request):
    def update(stage, percent, message):
        with state_lock:
            job = jobs[job_id]
            if job['cancel_requested']:
                raise Cancelled()
            job.update(status='running', stage=stage, percent=percent, message=message, updated_at=time.time())
    try:
        from api.routing import calculate_route
        result = calculate_route(request, update)
        with state_lock:
            job = jobs[job_id]
            if job['cancel_requested']:
                raise Cancelled()
            job.update(status='completed', result=result, percent=100, message='완료')
    except Cancelled:
        with state_lock:
            jobs[job_id].update(status='cancelled', message='취소됨')
    except RoutingError as error:
        with state_lock:
            jobs[job_id].update(status='failed', error=error.as_dict())
    except Exception:
        import logging
        logging.exception('Route job failed')
        with state_lock:
            jobs[job_id].update(status='failed', error={'code':'internal_error','message':'배차 처리 오류가 발생했습니다. 서버 로그를 확인해주세요.'})
    finally:
        with state_lock:
            jobs[job_id]['updated_at'] = time.time()
        work_lock.release()


@router.post('/route-jobs', status_code=202)
def create_job(request: RouteRequest):
    if not work_lock.acquire(blocking=False):
        raise HTTPException(409, '다른 배차 작업을 처리 중입니다. 완료 또는 취소 후 다시 시도해주세요.')
    job_id = uuid.uuid4().hex
    with state_lock:
        _cleanup()
        jobs[job_id] = dict(job_id=job_id, status='queued', percent=0, stage='queued',
                            message='계산 준비', cancel_requested=False, updated_at=time.time())
    try:
        executor.submit(_run, job_id, request)
    except Exception:
        work_lock.release()
        with state_lock:
            del jobs[job_id]
        raise
    return {'job_id':job_id}


@router.get('/route-jobs/{job_id}')
def get_job(job_id: str):
    with state_lock:
        _cleanup()
        if job_id not in jobs:
            raise HTTPException(404, '작업이 없거나 보관 시간이 지났습니다. 다시 계산해주세요.')
        return dict(jobs[job_id])


@router.delete('/route-jobs/{job_id}', status_code=202)
def cancel_job(job_id: str):
    with state_lock:
        if job_id not in jobs:
            raise HTTPException(404, '작업을 찾을 수 없습니다.')
        if jobs[job_id]['status'] not in ('completed','failed','cancelled'):
            jobs[job_id]['cancel_requested'] = True
            jobs[job_id]['message'] = '취소 요청됨: 현재 계산 단계가 끝나면 중단합니다.'
        return {'message':jobs[job_id]['message']}


def run_synchronous(request):
    if not work_lock.acquire(blocking=False):
        raise HTTPException(409, '다른 배차 작업을 처리 중입니다.')
    try:
        from api.routing import calculate_route
        return calculate_route(request)
    except RoutingError as error:
        raise HTTPException(503 if error.code == 'solver_unavailable' else 422, error.as_dict())
    finally:
        work_lock.release()
