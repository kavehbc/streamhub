"""Landing page, news page and board pages."""
import tornado.web

from streamhub import auth
from streamhub.handlers.base import BaseHandler


def board_apps(catalog, board_name):
    """[(app, [children])] listed on `board_name` ("" is the landing page)."""
    apps = []
    for app in catalog.apps:
        children = [c for c in app.children if board_name in c.boards]
        if board_name in app.boards:
            apps.append((app, children))
    return apps


class BoardPageHandler(BaseHandler):
    """Landing page (board "") and board pages ("/<name>.brd/")."""

    def get(self, board_name=""):
        catalog = self.hub.catalog
        if not board_name and auth.needs_setup(catalog, self.hub.settings):
            self.redirect("/setup/")  # a new hub: create the first admin before anything else
            return
        board = None
        if board_name:
            board = catalog.board(board_name)
            if board is None:
                raise tornado.web.HTTPError(404)
            if not auth.can_view_board(self.current_user, board):
                if self.current_user is None:
                    self.redirect(self.login_url())
                    return
                raise tornado.web.HTTPError(403)
        self.render_layout(view="board" if board_name else "home", board_name=board_name,
                           board_label=board.label if board else "")

    def render_layout(self, view, board_name="", board_label=""):
        """The `template-file` layout; `view` is home, news or board."""
        catalog, user = self.hub.catalog, self.current_user
        # Home page: each board with its number of visible apps, and whether this user can open it.
        board_cards = [(b, sum(1 for app, _ in board_apps(catalog, b.name) if app.display != "hidden"),
                        auth.can_view_board(user, b)) for b in catalog.boards]
        self.render(self.hub.settings.template_file,
                    view=view,
                    nav_active=board_name or view,
                    apps=board_apps(catalog, board_name),
                    board=board_name,
                    board_label=board_label,
                    board_cards=board_cards,
                    boards_list=catalog.boards,
                    user_access=user.boards if user else [],
                    news=catalog.news() if view != "board" else [],
                    cwd=str(self.hub.settings.config_dir))


class NewsPageHandler(BoardPageHandler):
    """Every announcement of the news file (the landing page shows the latest ones)."""

    def get(self):
        self.render_layout(view="news")
