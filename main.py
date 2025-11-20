import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

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


# ---------------- Participants ----------------
@app.post("/participants")
def create_participant(participant: Participant):
    participant_id = create_document("participant", participant)
    return {"id": participant_id}


@app.get("/participants")
def list_participants():
    docs = get_documents("participant")
    return [to_str_id(d) for d in docs]


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
    query = {}
    if room_id:
        query["room_id"] = room_id
    if day:
        query["stay_days"] = day
    docs = get_documents("assignment", query)
    return [to_str_id(d) for d in docs]


# ---------------- Summary / Dashboard ----------------
@app.get("/summary")
def summary():
    rooms = list(db.room.find())
    participants = list(db.participant.find())

    # Build occupancy per room per day
    occupancy = {}
    for r in rooms:
        rid = str(r["_id"])
        occupancy[rid] = {1: 0, 2: 0, 3: 0, "capacity": r.get("capacity", 0), "name": r.get("name")}

    for a in db.assignment.find():
        rid = a.get("room_id")
        for d in a.get("stay_days", []):
            if rid in occupancy and d in [1, 2, 3]:
                occupancy[rid][d] += 1

    total_participants = len(participants)
    total_rooms = len(rooms)

    return {
        "totals": {
            "participants": total_participants,
            "rooms": total_rooms
        },
        "occupancy": occupancy
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
