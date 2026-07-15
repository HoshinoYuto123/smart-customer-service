# Import all tool modules to trigger @tool_registry.register() decorators
from app.tools import faq_search       # noqa: F401
from app.tools import query_order      # noqa: F401
from app.tools import query_account    # noqa: F401
from app.tools import create_ticket    # noqa: F401
from app.tools import transfer_human   # noqa: F401
from app.tools import policy_search    # noqa: F401
