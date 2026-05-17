from flask import Flask

from .blueprints.api import api_bp
from .blueprints.stubs import stubs_bp
from .blueprints.ui import ui_bp
from .config import Config
from .extensions import init_controller


def create_app(config_cls: type[Config] = Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_cls)

    init_controller(app)

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(stubs_bp, url_prefix="/api")

    return app
