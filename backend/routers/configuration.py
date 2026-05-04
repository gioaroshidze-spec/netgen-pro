from fastapi import APIRouter, Depends, HTTPException
import schemas

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate):
    """
    Receives an AI prompt and target lists, then generates the configuration logic.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    # MOCK LOGIC: We will replace this with the real AI/Template engine later
    generated_text = f"! --- VNMS AI CONFIGURATION ENGINE ---\n"
    generated_text += f"! Interpreting prompt: '{request.prompt}'\n"
    generated_text += f"! Target Switches: {', '.join(request.switches) or 'None'}\n"
    generated_text += f"! Target Routers: {', '.join(request.routers) or 'None'}\n"
    generated_text += "!\n"
    generated_text += "vlan 10\n"
    generated_text += " name AI_GENERATED_VLAN\n"
    
    return {"status": "success", "config": generated_text}