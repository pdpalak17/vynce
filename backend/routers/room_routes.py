"""
Vynce Room Routes - CRUD for music rooms.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Room, User
from ..schemas import RoomCreate, RoomResponse
import json
from ..models import RoomLiveState

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new music room."""
    room = Room(
        name=payload.name,
        creator_id=user.id,
        is_public=payload.is_public,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)

    resp = RoomResponse.model_validate(room)
    resp.creator_username = user.username
    return resp


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active public rooms + user's own rooms."""
    # Get public rooms
    result = await db.execute(
        select(Room).where(Room.is_active == True).where(
            (Room.is_public == True) | (Room.creator_id == user.id)
        ).order_by(Room.created_at.desc()).limit(50)
    )
    rooms = result.scalars().all()

    response = []
    for room in rooms:
        r = RoomResponse.model_validate(room)
        r.creator_username = room.creator.username if room.creator else None
        
        state_result = await db.execute(select(RoomLiveState).where(RoomLiveState.room_code == room.code))
        live_state = state_result.scalar_one_or_none()
        if live_state and live_state.current_track:
            r.current_track = json.loads(live_state.current_track)
        r.listener_count = 0
        
        response.append(r)

    return response


@router.get("/{code}", response_model=RoomResponse)
async def get_room(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get room details by invite code."""
    code = code.upper()
    result = await db.execute(select(Room).where(Room.code == code))
    room = result.scalar_one_or_none()

    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    r = RoomResponse.model_validate(room)
    r.creator_username = room.creator.username if room.creator else None
    
    state_result = await db.execute(select(RoomLiveState).where(RoomLiveState.room_code == room.code))
    live_state = state_result.scalar_one_or_none()
    if live_state and live_state.current_track:
        r.current_track = json.loads(live_state.current_track)
    r.listener_count = 0
    
    return r


@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a room (owner only)."""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()

    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not room owner")

    room.is_active = False
    await db.commit()
    return {"message": "Room deleted successfully"}
