from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, extra_class=''):
    return format_html(
        '<svg class="ic {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>',
        extra_class, name,
    )


@register.filter
def uzs(value):
    """12345.5 -> '12 346 UZS'."""
    if value in (None, ''):
        return '—'
    try:
        return f'{float(value):,.0f}'.replace(',', ' ') + ' UZS'
    except (TypeError, ValueError):
        return value


@register.simple_tag(takes_context=True)
def query(context, **kwargs):
    """Current GET params with the given keys replaced (None/'' removes a key)."""
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        params.pop(key, None)
        if value not in (None, ''):
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'


@register.simple_tag(takes_context=True)
def t(context, text, **values):
    """{% t "People" %} -> text in the current language (English when no translation)."""
    from workspace.i18n import translate
    out = translate(context.get('lang', 'en'), text)
    return out.format(**values) if values else out


@register.filter
def tr(text, lang):
    """{{ item.label|tr:lang }} for labels that come from Python."""
    from workspace.i18n import translate
    return translate(lang, text)
