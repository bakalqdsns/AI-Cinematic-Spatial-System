"""
v2 API - Shot Management Endpoints.

Manages shots (camera takes) within a project:
  POST   /api/aicss/v2/projects/{projectId}/shots           — Create a shot
  GET    /api/aicss/v2/projects/{projectId}/shots           — List shots
  GET    /api/aicss/v2/projects/{projectId}/shots/{shotId}  — Get shot details
  DELETE /api/aicss/v2/projects/{projectId}/shots/{shotId}  — Delete a shot
  GET    /api/aicss/v2/projects/{projectId}/shots/{shotId}/frames/{frameIndex} — Get single frame
  GET    /api/aicss/v2/projects/{projectId}/shots/{shotId}/frames/{frameIndex}/image — Get frame image

Reference: docs/API_PROTOCOL_v2.md Section 7
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.project_store import project_store

_log = __import__("logging").getLogger("aicss")

router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────


class CreateShotRequest(BaseModel):
    shotId: str = Field(..., description="Shot ID")
    description: Optional[str] = Field(None, description="Shot description")
    sceneType: Optional[str] = Field(None, description="Scene type (e.g. indoor, outdoor)")


class ShotResponse(BaseModel):
    shotId: str
    projectId: str
    createdAt: str
    updatedAt: str
    status: str
    frameCount: int
    description: Optional[str] = None
    sceneType: Optional[str] = None


class ShotListResponse(BaseModel):
    count: int
    shots: list[ShotResponse]


class FrameResponse(BaseModel):
    frameIndex: int
    frameId: str
    frameType: Optional[str] = None
    originalUrl: str
    depthMapUrl: str
    objects: list[dict]
    layers: list[dict]
    globalObjectIds: dict[str, str]


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/v2/projects/{project_id}/shots",
    response_model=ShotResponse,
    status_code=201,
)
async def create_shot(project_id: str, request: CreateShotRequest):
    """
    Create a new shot under a project.

    Creates the shot directory structure and initializes manifest.json.
    """
    try:
        manifest = await project_store.create_shot(
            project_id=project_id,
            shot_id=request.shotId,
            description=request.description,
            scene_type=request.sceneType,
        )
        return ShotResponse(
            shotId=manifest.shot_id,
            projectId=manifest.project_id,
            createdAt=manifest.created_at,
            updatedAt=manifest.updated_at,
            status=manifest.status,
            frameCount=manifest.frame_count,
            description=manifest.description,
            sceneType=manifest.scene_type,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _log.exception(f"[shots] Failed to create shot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create shot: {e}")


@router.get(
    "/v2/projects/{project_id}/shots",
    response_model=ShotListResponse,
)
async def list_shots(project_id: str):
    """
    List all shots under a project.
    """
    try:
        summaries = await project_store.list_shots(project_id)
        return ShotListResponse(
            count=len(summaries),
            shots=[
                ShotResponse(
                    shotId=s.shot_id,
                    projectId=s.project_id,
                    createdAt=s.created_at,
                    updatedAt=s.updated_at,
                    status=s.status,
                    frameCount=s.frame_count,
                    description=s.description,
                    sceneType=s.scene_type,
                )
                for s in summaries
            ],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _log.exception(f"[shots] Failed to list shots: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list shots: {e}")


@router.get(
    "/v2/projects/{project_id}/shots/{shot_id}",
    response_model=ShotResponse,
)
async def get_shot(project_id: str, shot_id: str):
    """
    Get shot details including frame list.
    """
    try:
        manifest = await project_store.get_shot(project_id, shot_id)
        return ShotResponse(
            shotId=manifest.shot_id,
            projectId=manifest.project_id,
            createdAt=manifest.created_at,
            updatedAt=manifest.updated_at,
            status=manifest.status,
            frameCount=manifest.frame_count,
            description=manifest.description,
            sceneType=manifest.scene_type,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _log.exception(f"[shots] Failed to get shot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get shot: {e}")


@router.delete(
    "/v2/projects/{project_id}/shots/{shot_id}",
)
async def delete_shot(project_id: str, shot_id: str):
    """
    Delete a shot and all its frames.
    """
    deleted = await project_store.delete_shot(project_id, shot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    return {"ok": True, "projectId": project_id, "shotId": shot_id, "deleted": True}


@router.get(
    "/v2/projects/{project_id}/shots/{shot_id}/frames/{frame_index}",
    response_model=FrameResponse,
)
async def get_frame(project_id: str, shot_id: str, frame_index: int):
    """
    Get single frame analysis result.
    """
    try:
        data = await project_store.load_frame(project_id, shot_id, frame_index)
        return FrameResponse(
            frameIndex=data.get("frameIndex", frame_index),
            frameId=data.get("frameId", ""),
            frameType=data.get("frameType"),
            originalUrl="",  # URL constructed by frontend from project_store
            depthMapUrl=data.get("depthMapUrl", ""),
            objects=data.get("objects", []),
            layers=data.get("layers", []),
            globalObjectIds=data.get("globalObjectIds", {}),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _log.exception(f"[shots] Failed to get frame: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get frame: {e}")


@router.get(
    "/v2/projects/{project_id}/shots/{shot_id}/frames/{frame_index}/image",
)
async def get_frame_image(
    project_id: str,
    shot_id: str,
    frame_index: int,
    kind: Literal["original", "depth"] = "original",
):
    """
    Get frame image (original or depth map) as binary PNG.

    Args:
        kind: "original" for raw frame, "depth" for depth map
    """
    try:
        image_bytes = await project_store.load_frame_image(
            project_id, shot_id, frame_index, kind=kind
        )
        return Response(content=image_bytes, media_type="image/png")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _log.exception(f"[shots] Failed to get frame image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get frame image: {e}")
