from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from routers.auth import get_current_admin, get_current_user

router = APIRouter(tags=["Organization"])

@router.get("/organization/hierarchy", response_model=list[schemas.BuildingResponse])
def get_hierarchy(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Returns the complete nested JSON structure of Buildings -> Floors -> Zones."""
    return db.query(models.Building).all()

@router.post("/organization/building", response_model=schemas.BuildingResponse)
def create_building(bldg: schemas.BuildingCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    db_bldg = models.Building(name=bldg.name)
    db.add(db_bldg)
    db.commit()
    db.refresh(db_bldg)
    return db_bldg

@router.post("/organization/floor", response_model=schemas.FloorResponse)
def create_floor(floor: schemas.FloorCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    bldg = db.query(models.Building).filter(models.Building.id == floor.building_id).first()
    if not bldg: raise HTTPException(status_code=404, detail="Building not found.")
    db_floor = models.Floor(name=floor.name, building_id=floor.building_id)
    db.add(db_floor)
    db.commit()
    db.refresh(db_floor)
    return db_floor

@router.post("/organization/zone", response_model=schemas.ZoneResponse)
def create_zone(zone: schemas.ZoneCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    floor = db.query(models.Floor).filter(models.Floor.id == zone.floor_id).first()
    if not floor: raise HTTPException(status_code=404, detail="Floor not found.")
    db_zone = models.Zone(name=zone.name, floor_id=zone.floor_id)
    db.add(db_zone)
    db.commit()
    db.refresh(db_zone)
    return db_zone

@router.delete("/organization/building/{bldg_id}")
def delete_building(bldg_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    bldg = db.query(models.Building).filter(models.Building.id == bldg_id).first()
    if not bldg: raise HTTPException(status_code=404, detail="Building not found.")
    db.delete(bldg) # Cascades and deletes floors/zones due to ORM config
    db.commit()
    return {"message": "Building deleted."}

@router.delete("/organization/floor/{floor_id}")
def delete_floor(floor_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    floor = db.query(models.Floor).filter(models.Floor.id == floor_id).first()
    if not floor: raise HTTPException(status_code=404, detail="Floor not found.")
    db.delete(floor)
    db.commit()
    return {"message": "Floor deleted."}

@router.delete("/organization/zone/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_admin)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone: raise HTTPException(status_code=404, detail="Zone not found.")
    db.delete(zone)
    db.commit()
    return {"message": "Zone deleted."}