"""
Excel Export API
"""
import io
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from export.excel_exporter import ExcelExporter

router = APIRouter()


class ExportRequest(BaseModel):
    routes: List[Dict[str, Any]]
    destination: Dict[str, Any]
    summary: Optional[Dict[str, Any]] = None


@router.post("/export")
async def export_excel(request: ExportRequest):
    """
    노선 결과를 Excel 파일로 Export
    """
    try:
        exporter = ExcelExporter()
        excel_bytes = exporter.export(
            routes=request.routes,
            destination=request.destination,
            summary=request.summary
        )

        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=bus_routes.xlsx"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export 오류: {str(e)}")
