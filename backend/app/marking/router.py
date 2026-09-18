from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from ..auth import current_user
from ..common import envelope
from ..schemas import Envelope
from .models import MarkingInput,MarkingOutput
from .service import ExamMarkingTool

router=APIRouter(prefix='/api/v1/marking',tags=['marking-tools'])

def tool(request):
    return ExamMarkingTool(request.app.state.db,request.app.state.marking_provider)

@router.post('/jobs',response_model=Envelope[MarkingOutput],status_code=202)
def submit(body:MarkingInput,request:Request,user=Depends(current_user)):
    return envelope(tool(request).submit(user['id'],body))

@router.get('/jobs/{job_id}',response_model=Envelope[MarkingOutput])
def get(job_id:str,request:Request,user=Depends(current_user)):
    return envelope(tool(request).get(user['id'],job_id))

@router.get('/jobs/{job_id}/image',response_class=FileResponse)
def image(job_id:str,request:Request,user=Depends(current_user)):
    return FileResponse(tool(request).image_path(user['id'],job_id),media_type='image/png',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
