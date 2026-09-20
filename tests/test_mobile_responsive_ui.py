from app.saas.course_studio_ui import CSS as COURSE_STUDIO_CSS
from app.saas.job_detail_ui import CSS as JOB_DETAIL_CSS
from app.saas.operations_ui import JS as OPERATIONS_JS
from app.saas.theme_ui import CSS as THEME_CSS
from app.saas.web import HTML


def test_mobile_shell_uses_dynamic_viewport_and_safe_area():
    assert "viewport-fit=cover" in HTML
    assert "100dvh" in THEME_CSS
    assert "safe-area-inset-bottom" in THEME_CSS
    assert "scroll-snap-type:x proximity" in THEME_CSS
    mobile = THEME_CSS.split("/* Mobile Responsive V2 */")[-1]
    assert "grid-template-columns:repeat(7,1fr)" not in mobile
    assert ".sidebar{" in mobile
    assert "height:auto;" in mobile
    assert "min-height:0;" in mobile


def test_course_studio_has_touch_friendly_mobile_controls():
    mobile = COURSE_STUDIO_CSS.split("/* Mobile Responsive V2 */")[-1]
    assert "height:100dvh" in mobile
    assert ".resize-dot" in mobile
    assert "width:26px;height:26px" in mobile
    assert "env(safe-area-inset-bottom)" in mobile
    assert "font-size:16px" in mobile


def test_job_detail_mobile_view_uses_dynamic_height_and_horizontal_phases():
    mobile = JOB_DETAIL_CSS.split("/* Mobile Responsive V2 */")[-1]
    assert "height:100dvh" in mobile
    assert "overflow-x:auto" in mobile
    assert "scroll-snap-type:x proximity" in mobile
    assert "env(safe-area-inset-bottom)" in mobile


def test_operations_console_stacks_on_narrow_phones():
    assert "@media(max-width:460px)" in OPERATIONS_JS
    assert ".ops-kpis,.ops-detail-grid{grid-template-columns:1fr}" in OPERATIONS_JS
    assert ".ops-search{width:100%;min-width:0}" in OPERATIONS_JS
