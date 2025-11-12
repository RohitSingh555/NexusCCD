from django import template
from django.http import QueryDict

register = template.Library()


@register.simple_tag(takes_context=True)
def query_string_with_page(context, page_number):
    """
    Generate a query string preserving all GET parameters except 'page',
    and add/update the 'page' parameter with the given page_number.
    
    Usage: {% query_string_with_page 2 %}
    """
    request = context.get('request')
    if not request:
        return f'?page={page_number}'
    
    # Create a mutable copy of GET parameters
    params = QueryDict(mutable=True)
    params.update(request.GET)
    
    # Remove the 'page' parameter if it exists
    if 'page' in params:
        del params['page']
    
    # Add the new page number
    params['page'] = str(page_number)
    
    # Generate the query string
    query_string = params.urlencode()
    return f'?{query_string}' if query_string else f'?page={page_number}'

