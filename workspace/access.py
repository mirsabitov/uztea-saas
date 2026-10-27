"""Access control and navigation for the workspace.

The workspace is a staff-only UI layer. It reads data directly and hands every
change (edit, import/export, bulk actions, payment tools) to the existing
Django admin views, so admin permission checks stay the single source of truth.
"""
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.csrf import csrf_protect

# Section key -> (label, url name, icon, permissions: any one of them grants access)
NAV_SECTIONS = [
    ('home', 'Home', 'workspace:home', 'home', ()),
    ('people', 'People', 'workspace:people', 'users', (
        'app.view_membership', 'app.view_pendingpayment', 'app.view_teacherbank',
    )),
    ('forms', 'Forms & Events', 'workspace:forms', 'file-text', (
        'app.view_membership', 'app.view_conferenceregistration', 'app.view_anniversaryregistration',
        'workspace.view_event',
    )),
    ('payments', 'Payments', 'workspace:payments', 'credit-card', (
        'click.view_order', 'app.view_pendingpayment', 'atmos.view_atmostransaction',
        'payme.view_paymetransaction', 'click.view_promocode',
    )),
    ('partners', 'Partners', 'workspace:partners', 'handshake', ('app.view_partner', 'workspace.view_benefit')),
    ('certificates', 'Certificates', 'workspace:certificates', 'award', (
        'certificates.view_certificatetemplate', 'certificates.view_certificate',
    )),
    ('settings', 'Settings', 'workspace:settings', 'settings', (
        'app.view_membershiptypeconfig', 'auth.view_user', 'auth.view_group',
    )),
    # uztea.uz content (news, events, pages) — placeholder until the website phase.
    ('website', 'Website', 'workspace:website', 'globe', ()),
]
SECTION_PERMS = {key: perms for key, _label, _url, _icon, perms in NAV_SECTIONS}
# Sections reached from the header rather than the sidebar.
SECTION_PERMS['saas'] = ('workspace.view_organizationsettings', 'workspace.change_organizationsettings')


def can(user, *perms):
    """True when the user has at least one of the permissions (or none are required)."""
    return not perms or any(user.has_perm(p) for p in perms)


def admin_url(name, *args, query=None):
    """Reverse an admin URL, or None when it does not exist."""
    try:
        url = reverse(f'admin:{name}', args=args)
    except NoReverseMatch:
        return None
    if query:
        url += '?' + urlencode(query)
    return url


def nav_items(user, current):
    items = []
    for key, label, url_name, icon, perms in NAV_SECTIONS:
        if can(user, *perms):
            items.append({'key': key, 'label': label, 'url': reverse(url_name),
                          'icon': icon, 'active': key == current})
    return items


def user_role(user):
    if user.is_superuser:
        return 'Administrator'
    group = user.groups.order_by('name').values_list('name', flat=True).first()
    return group or 'Staff'


def workspace_view(section, *perms):
    """Staff-only view; `perms` narrows access further (any one is enough).

    With no `perms` the section's navigation permissions apply.
    """
    required = perms or SECTION_PERMS.get(section, ())

    def decorator(view):
        # The project's CSRF middleware is off. Protecting every workspace view sets the
        # CSRF cookie on pages that render forms and checks every POST they send.
        @csrf_protect
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_active or not user.is_staff:
                login = reverse('admin:login') + '?' + urlencode({'next': request.get_full_path()})
                return redirect(login)
            if not can(user, *required):
                return render_ws(request, 'workspace/forbidden.html', {}, section, status=403)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def render_ws(request, template, context, section, status=200):
    user = request.user
    from .i18n import LANGUAGES, language_for
    from .models import OrganizationSettings
    lang = language_for(request)
    org = OrganizationSettings.get()
    base = {
        'org': org,
        'brand': org.logo_urls(),
        'lang': lang,
        'languages': LANGUAGES,
        'nav': nav_items(user, section),
        'can_saas': can(user, *SECTION_PERMS['saas']),
        'section': section,
        'user_role': user_role(user),
        'user_initials': initials(user.get_full_name() or user.get_username()),
        'debug_mode': settings.DEBUG,
        'admin_index_url': admin_url('index'),
        'password_change_url': admin_url('password_change'),
        'logout_url': admin_url('logout'),
    }
    base.update(context)
    return render(request, template, base, status=status)


def initials(name):
    parts = [p for p in (name or '').replace('.', ' ').split() if p]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
