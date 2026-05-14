from fastapi import APIRouter, Depends, HTTPException
import schemas
import os
from litellm import completion

router = APIRouter(tags=["Configuration Engine"])

@router.post("/configuration/generate")
def generate_configuration(request: schemas.AIConfigGenerate):
    """
    Receives an AI prompt and target lists, then generates the configuration logic
    using the active LLM via LiteLLM.
    """

    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    
    # 1. Format the targets so that AI knows what devices it is configuring
    switches_str = ", ".join(request.switches) if request.switches else "None"
    routers_str = ", ".join(request.routers) if request.routers else "None"

    # 2. Define the System Prompt (The "Rules" for the AI)
    system_prompt = (
        "You are an exper, senior Enterprise Network Engineer. "
        "Your job is to generate strict, production-ready configuration commands (Cisco IOS by default unless specified, if specified it would be HPE, Aruba, Mikrotik) "
        "Do not include conversational filler, markdown formatting blocks like '''bash, or explanations. "
        "ONLY output the raw configuration lines and necessary comments starting with '!'. "
    )

    # 3. Define the User Prompt (What you typed in the UI)
    user_prompt = f"""
    Target Switches: {switches_str}
    Target Routers: {routers_str}

    Network Requirement: {request.prompt}
    """

    try:
        # Fetch the model from .env (defautls to Claude 3 Opus if not found)
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7")

        # 4. Make the call to the AI Provider using LiteLLM
        response = completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],

        )

        # 5. Extract the text and return it to React
        generated_config = response.choices[0].message.content

        # Add a nice header for the UI
        final_output = f"! --- VNMS AI Generated Configuration ---\n"
        final_output += f"! Model: {model_name}\n!\n"
        final_output += generated_config

        return {"status": "success", "config": final_output}
    
    except Exception as e:
        # If your API key is missing or ivalid, it will safely throw an error here
        print(f"LiteLLM Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Engine Error: Check console for details. ")