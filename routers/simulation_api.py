"""TAI Simulation API v1.0.0
Prefix: /simulation
Deterministic Runtime Verification.
"""
from fastapi import APIRouter,HTTPException,Query
from schemas.simulation import ScenarioIn,RunSimulationIn
from services import simulation_svc as svc

router=APIRouter(prefix="/simulation",tags=["시뮬레이션"])

@router.post("/scenarios")
def create_scenario(body:ScenarioIn):
    try:return{"status":"success","data":svc.create_scenario(body.dict())}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/scenarios")
def list_scenarios(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return{"status":"success","data":svc.list_scenarios(page,page_size)}

@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id:str):
    r=svc.get_scenario(scenario_id)
    if not r:raise HTTPException(404,"scenario not found")
    return{"status":"success","data":r}

@router.post("/run")
def run_simulation(body:RunSimulationIn):
    try:return{"status":"success","data":svc.run_simulation(body.scenario_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.post("/verify-deterministic")
def verify_deterministic(body:RunSimulationIn):
    try:return{"status":"success","data":svc.verify_deterministic(body.scenario_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/results/{scenario_id}")
def get_result(scenario_id:str):
    return{"status":"success","data":svc.get_result(scenario_id)}
