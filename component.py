"""غلاف مكوّن واجهة الخريطة (masar_ui)."""
from pathlib import Path

import streamlit.components.v1 as components

_DIR = Path(__file__).parent / 'masar_ui'
_COMPONENT = components.declare_component('masar_ui', path=str(_DIR))


def masar_ui(data, key='masar_ui'):
    """يرسم واجهة الخريطة. يرجع آخر حدث من المستخدم (بحث أو تبديل المظهر) أو None."""
    return _COMPONENT(data=data, key=key, default=None)