from fastapi import FastAPI,Request,Depends,Form
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from database_config import Base, engine, get_db
from fastapi.staticfiles import StaticFiles

from models import Visitor
from logger import get_logger

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Visitor Book"
) 

logger = get_logger(__name__)
logger.info("Starting the FastAPI application")


app.mount("/static",StaticFiles(directory="static"),name="static")

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    logger.info({
        "event": "get_visitors_request",
        "path": "/",
        "client_host": request.client.host if request.client else "unknown",
    })
    try:
        visitors = db.query(Visitor).order_by(Visitor.id).all()
        logger.info({
            "event": "get_visitors_success",
            "path": "/",
            "visitor_count": len(visitors),
        })
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "visitors": visitors}
        )
    except SQLAlchemyError as e:
        logger.error(
            {"event": "get_visitors_db_error", "path": "/", "error": str(e)},
            exc_info=True
        )
        return templates.TemplateResponse(
            "errors.html",
            {"request": request, "detail": "Could not retrieve visitors."},
            status_code=500
        )
    except Exception as e:
         logger.error(
            {"event": "get_visitors_unexpected_error", "path": "/", "error": str(e)},
            exc_info=True
        )
         return templates.TemplateResponse(
            "errors.html",
            {"request": request, "detail": "An unexpected error occurred."},
            status_code=500
        )


@app.post("/add", response_class=RedirectResponse)
async def add_visitor(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    visitor_name = name.strip()
    client_host = request.client.host if request.client else "unknown"
    log_context = {
        "path": "/add",
        "submitted_name": name, 
        "processed_name": visitor_name,
        "client_host": client_host,
    }

    logger.info({"event": "add_visitor_request", **log_context})

    if visitor_name:
        try:
            db_visitor = Visitor(name=visitor_name)
            db.add(db_visitor)
            db.commit()
            db.refresh(db_visitor)
            logger.info({
                "event": "add_visitor_success",
                "visitor_id": db_visitor.id,
                 **log_context 
            })
        except SQLAlchemyError as e:
            logger.error(
                {"event": "add_visitor_db_error", "error": str(e), **log_context},
                exc_info=True
            )
            db.rollback()
        except Exception as e:
             logger.error(
                {"event": "add_visitor_unexpected_error", "error": str(e), **log_context},
                exc_info=True
            )
             db.rollback()
    else:
        logger.warning({"event": "add_visitor_empty_name", **log_context})
    return RedirectResponse(url="/", status_code=303)


@app.get("/health", status_code=200)
async def health_check():
    logger.debug({"event": "health_check"})
    return {"status": "ok"}