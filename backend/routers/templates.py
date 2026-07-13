from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
import json
import os
from litellm import completion
from logger import log_event
from routers.auth import get_current_user

router = APIRouter(tags=["Templates"])

@router.post("/templates/", response_model=schemas.TemplateResponse)
def create_template(template: schemas.TemplateCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """
    Saves a configuration JSON as a template and uses AI to auto-generate a description.
    """
    # 1. Ask AI to generate a description
    try:
        model_name = os.getenv("ACTIVE_AI_MODEL", "claude-opus-4-7")
        system_prompt = "You are a senior network architect. Summarize the following JSON network configuration in exactly ONE clear, concise sentence. Focus on the core purpose (e.g., 'Configures VLANs 10 and 20 on edge switches.'). Do not include introductory text."
        user_prompt = f"Summarize this JSON config:\n{json.dumps(template.payload, indent=2)}"

        response = completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        ai_description = response.choices[0].message.content.strip()

        # Clean up quotes if the AI accidentally wraps the sentence in them
        if ai_description.startswith('"') and ai_description.endswith('"'):
            ai_description = ai_description[1:-1]
    
    except Exception as e:
        print(f"Failed to generate AI description: {e}")
        ai_description = "Custom network configuration template."
    
    # 2. Save to Database
    db_template = models.ConfiguraitonTemplate(
        name=template.name,
        category=template.category,
        description=ai_description,
        payload=template.payload
    )

    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    # 3. Log the creation in our event Logs
    prompt_used = template.prompt if template.prompt else "Derived from live AI generation session"

    log_event(
        db=db,
        event_type="Configuration",
        severity="INFO",
        author=current_user.username,
        target_devices=[],
        details={
            "action": "Template Saved", 
            "template_name": template.name,
            "category": template.category, 
            "ai_description": ai_description,
            "prompt": prompt_used,  # <-- Now passing the exact user prompt
            "generated_commands": json.dumps(template.payload, indent=2)
        }
    )

    return db_template

@router.get("/templates/", response_model=list[schemas.TemplateResponse])
def get_templates(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fetches all saved templates ordered by newest first."""
    return db.query(models.ConfiguraitonTemplate).order_by(models.ConfiguraitonTemplate.created_at.desc()).all()

@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Deletes a specific template."""
    db_template = db.query(models.ConfiguraitonTemplate).filter(models.ConfiguraitonTemplate.id == template_id).first()
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template_name = db_template.name
    db.delete(db_template)
    db.commit()

    log_event(
        db=db,
        event_type="Configuration",
        severity="WARNING",
        author=current_user.username,
        target_devices=[],
        details={"action": "Template Deleted", "template_name": template_name}
    )

    return {"message": "Template deleted successfully"}