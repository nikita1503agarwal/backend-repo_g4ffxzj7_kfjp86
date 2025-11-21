import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents
from schemas import Room, Participant, Assignment

app = FastAPI(title="Retraite - Gestion Hébergements")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class ObjectIdStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        try:
            ObjectId(str(v))
            return str(v)
        except Exception:
            raise ValueError("Invalid ObjectId string")


def to_str_id(doc):
    if doc is None:
        return None
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d


def now_utc():
    return datetime.now(timezone.utc)


@app.get("/")
def read_root():
    return {"message": "API Gestion Hébergements - Retraite 3 jours"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# ---------------- Rooms ----------------
@app.post("/rooms")
def create_room(room: Room):
    room_id = create_document("room", room)
    return {"id": room_id}


@app.get("/rooms")
def list_rooms():
    docs = get_documents("room")
    return [to_str_id(d) for d in docs]


@app.put("/rooms/{room_id}")
def update_room(room_id: str, payload: Dict[str, Any]):
    # Validate id
    try:
        rid = ObjectId(room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    # Only allow known fields
    allowed = {"name", "capacity", "gender", "type", "cooling", "amenities"}
    data = {k: v for k, v in payload.items() if k in allowed}
    if not data:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")

    res = db.room.update_one({"_id": rid}, {"$set": {**data, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Chambre introuvable")
    doc = db.room.find_one({"_id": rid})
    return to_str_id(doc)


@app.delete("/rooms/{room_id}")
def delete_room(room_id: str):
    try:
        rid = ObjectId(room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    # Prevent deletion if assignments exist
    if db.assignment.count_documents({"room_id": str(rid)}) > 0:
        raise HTTPException(status_code=409, detail="Impossible de supprimer: des attributions existent")

    res = db.room.delete_one({"_id": rid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chambre introuvable")
    return {"status": "deleted"}


# ---------------- Participants ----------------
@app.post("/participants")
def create_participant(participant: Participant):
    participant_id = create_document("participant", participant)
    return {"id": participant_id}


@app.get("/participants")
def list_participants():
    docs = get_documents("participant")
    return [to_str_id(d) for d in docs]


@app.put("/participants/{participant_id}")
def update_participant(participant_id: str, payload: Dict[str, Any]):
    try:
        pid = ObjectId(participant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    allowed = {"full_name", "email", "phone", "gender", "parish", "special_needs", "preference"}
    data = {k: v for k, v in payload.items() if k in allowed}
    if not data:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")

    res = db.participant.update_one({"_id": pid}, {"$set": {**data, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Participant introuvable")
    doc = db.participant.find_one({"_id": pid})
    return to_str_id(doc)


@app.delete("/participants/{participant_id}")
def delete_participant(participant_id: str):
    try:
        pid = ObjectId(participant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    # Prevent deletion if assignments exist
    if db.assignment.count_documents({"participant_id": str(pid)}) > 0:
        raise HTTPException(status_code=409, detail="Impossible de supprimer: des attributions existent")

    res = db.participant.delete_one({"_id": pid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Participant introuvable")
    return {"status": "deleted"}


# ---------------- Assignments ----------------
class AssignmentIn(Assignment):
    pass


@app.post("/assignments")
def create_assignment(assignment: AssignmentIn):
    # Basic validation for days subset
    for d in assignment.stay_days:
        if d not in [1, 2, 3]:
            raise HTTPException(status_code=400, detail="Les jours doivent être parmi 1,2,3")

    # Check room and participant exist
    try:
        pid = ObjectId(assignment.participant_id)
        rid = ObjectId(assignment.room_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiants invalides")

    if db.participant.find_one({"_id": pid}) is None:
        raise HTTPException(status_code=404, detail="Participant introuvable")
    if db.room.find_one({"_id": rid}) is None:
        raise HTTPException(status_code=404, detail="Chambre introuvable")

    # Occupancy check per day against room capacity
    room = db.room.find_one({"_id": rid})
    for day in assignment.stay_days:
        count = db.assignment.count_documents({"room_id": str(rid), "stay_days": day})
        if count >= room.get("capacity", 0):
            raise HTTPException(status_code=409, detail=f"Capacité atteinte pour le jour {day}")

    assignment_id = create_document("assignment", assignment)
    return {"id": assignment_id}


@app.get("/assignments")
def list_assignments(room_id: Optional[str] = None, day: Optional[int] = None):
    query: Dict[str, Any] = {}
    if room_id:
        query["room_id"] = room_id
    if day:
        query["stay_days"] = day
    docs = get_documents("assignment", query)
    return [to_str_id(d) for d in docs]


@app.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: Dict[str, Any]):
    try:
        aid = ObjectId(assignment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    doc = db.assignment.find_one({"_id": aid})
    if not doc:
        raise HTTPException(status_code=404, detail="Attribution introuvable")

    allowed = {"participant_id", "room_id", "stay_days"}
    data = {k: v for k, v in payload.items() if k in allowed}
    if not data:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")

    # If participant or room changes, validate existence
    participant_id = data.get("participant_id", doc.get("participant_id"))
    room_id = data.get("room_id", doc.get("room_id"))
    stay_days = data.get("stay_days", doc.get("stay_days", []))

    try:
        pid = ObjectId(str(participant_id))
        rid = ObjectId(str(room_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiants invalides")

    if db.participant.find_one({"_id": pid}) is None:
        raise HTTPException(status_code=404, detail="Participant introuvable")
    room = db.room.find_one({"_id": rid})
    if room is None:
        raise HTTPException(status_code=404, detail="Chambre introuvable")

    # Validate days
    for d in stay_days:
        if d not in [1, 2, 3]:
            raise HTTPException(status_code=400, detail="Les jours doivent être parmi 1,2,3")

    # Occupancy check per day against room capacity considering this assignment moves
    for day in stay_days:
        count = db.assignment.count_documents({"room_id": str(rid), "stay_days": day, "_id": {"$ne": aid}})
        if count >= room.get("capacity", 0):
            raise HTTPException(status_code=409, detail=f"Capacité atteinte pour le jour {day}")

    res = db.assignment.update_one({"_id": aid}, {"$set": {**data, "updated_at": now_utc()}})
    doc2 = db.assignment.find_one({"_id": aid})
    return to_str_id(doc2)


@app.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: str):
    try:
        aid = ObjectId(assignment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide")

    res = db.assignment.delete_one({"_id": aid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Attribution introuvable")
    return {"status": "deleted"}


# ---------------- Summary / Dashboard ----------------
@app.get("/summary")
def summary():
    rooms = list(db.room.find())
    participants = list(db.participant.find())

    # Build occupancy per room per day
    occupancy: Dict[str, Dict[str, Any]] = {}
    per_day_totals = {1: 0, 2: 0, 3: 0}
    per_day_capacity = {1: 0, 2: 0, 3: 0}

    cooling_counts = {"ventilated": 0, "air_conditioned": 0}
    type_counts = {"dorm": 0, "double": 0, "private": 0}

    for r in rooms:
        rid = str(r["_id"])
        occupancy[rid] = {1: 0, 2: 0, 3: 0, "capacity": r.get("capacity", 0), "name": r.get("name"), "cooling": r.get("cooling", "ventilated"), "type": r.get("type")}
        # capacity is available every day equally
        for d in [1, 2, 3]:
            per_day_capacity[d] += r.get("capacity", 0)
        cooling = r.get("cooling", "ventilated")
        if cooling in cooling_counts:
            cooling_counts[cooling] += 1
        t = r.get("type")
        if t in type_counts:
            type_counts[t] += 1

    for a in db.assignment.find():
        rid = a.get("room_id")
        for d in a.get("stay_days", []):
            if rid in occupancy and d in [1, 2, 3]:
                occupancy[rid][d] += 1
                per_day_totals[d] += 1

    total_participants = len(participants)
    total_rooms = len(rooms)

    participants_gender = {"male": 0, "female": 0, "unknown": 0}
    for p in participants:
        g = p.get("gender") or "unknown"
        if g not in participants_gender:
            g = "unknown"
        participants_gender[g] += 1

    per_day_remaining = {d: max(per_day_capacity[d] - per_day_totals[d], 0) for d in [1, 2, 3]}

    return {
        "totals": {
            "participants": total_participants,
            "rooms": total_rooms
        },
        "participants_gender": participants_gender,
        "rooms_by_cooling": cooling_counts,
        "rooms_by_type": type_counts,
        "per_day": {
            "capacity": per_day_capacity,
            "assigned": per_day_totals,
            "remaining": per_day_remaining
        },
        "occupancy": occupancy
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
