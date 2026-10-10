from fastapi import APIRouter

from app.api import auth, clipper, files, images, music, projects, slides, system, tts, video

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(projects.router)
api_router.include_router(slides.router)
api_router.include_router(tts.router)
api_router.include_router(video.router)
api_router.include_router(files.router)
api_router.include_router(music.router)
api_router.include_router(images.router)
api_router.include_router(clipper.router)
