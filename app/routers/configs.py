from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_admin_user, get_current_user
from ..models import User
from ..schemas import ConfigOut
from ..crud import configs as crud_configs
from ..services.qr import make_qr_data_uri

router = APIRouter(prefix='/configs')


@router.get('/my', response_model=list[ConfigOut])
def api_my_configs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return crud_configs.list_for_user(db, current_user.id)


@router.get('/my/{config_id}/download')
def download_my_config(config_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    config = crud_configs.get_for_user(db, config_id, current_user.id)
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    return Response(config.config_text, media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="{config.config_name}.conf"',
        'Cache-Control': 'no-store',
    })


@router.post('/my/{config_id}/note')
def update_my_note(
    config_id: int,
    note: str = Form(default=''),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = crud_configs.get_for_user(db, config_id, current_user.id)
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    config.user_note = (note or '').strip()[:1000] or None
    db.commit()
    return RedirectResponse(url='/cabinet?note_saved=1#my-configs', status_code=303)


@router.get('/admin/{config_id}/download')
def download_admin_config(config_id: int, db: Session = Depends(get_db), _: User = Depends(get_admin_user)):
    config = crud_configs.get(db, config_id)
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    return Response(config.config_text, media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="{config.config_name}.conf"',
        'Cache-Control': 'no-store',
    })


@router.get('/my/{config_id}/qr')
def my_qr(config_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    config = crud_configs.get_for_user(db, config_id, current_user.id)
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    return {'qr': make_qr_data_uri(config.config_text)}
