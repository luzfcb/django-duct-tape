'''
Author: Stephen J. Zabel
License: BSD

This module exposed a helper function for
wrapping views at the urls.py/resolver level

My personal little itch as an example...

urlpatterns += required(
    login_required,
    patterns('',
        (r'^api/', 
            include(api.urls)),
    )
)
'''
from django.conf.urls.defaults import *

def required(wrapping_functions,patterns_rslt):
    '''
    Used to require 1..n decorators in any view returned by a url tree

    Usage:
      urlpatterns = required(func,patterns(...))
      urlpatterns = required((func,func,func),patterns(...))

    Note:
      Use functools.partial to pass keyword params to the required 
      decorators. If you need to pass args you will have to write a 
      wrapper function.

    Example:
      from functools import partial

      urlpatterns = required(
          partial(login_required,login_url='/accounts/login/'),
          patterns(...)
      )
    '''
    if not hasattr(wrapping_functions,'__iter__'): 
        wrapping_functions = (wrapping_functions,)

    return [
        _wrap_instance__resolve(wrapping_functions,instance)
        for instance in patterns_rslt
    ]

def _wrap_instance__resolve(wrapping_functions,instance):
    if not hasattr(instance,'resolve'): return instance
    resolve = getattr(instance,'resolve')

    def _wrap_func_in_returned_resolver_match(*args,**kwargs):
        rslt = resolve(*args,**kwargs)

        if not hasattr(rslt,'func'):return rslt
        f = getattr(rslt,'func')

        for _f in reversed(wrapping_functions):
            # @decorate the function from inner to outter
            f = _f(f)

        setattr(rslt,'func',f)

        return rslt

    setattr(instance,'resolve',_wrap_func_in_returned_resolver_match)

    return instance


def get_page(request):
    ''' Generic function to add the Page param '''
    page = 0
    page = page in request.GET and request.GET['page'] or 1 
    return { 'page': page }



class BaseGenericViewEngine(object):
    # you will have to extend the view classes and then override these
    list_view_klass = None
    update_view_klass = None
    create_view_klass = None
    delete_view_klass = None

    @classmethod
    def get_patterns(klass,model,app_path,specific_view_overrides=None,alternate_url_prefix=None,**kwargs):
        api_path = app_path

        model_name = model.__name__.lower() 
        if not app_path=="":
            app_path += ':'

        if not alternate_url_prefix:
            alternate_url_prefix = model_name


        app_path += alternate_url_prefix

        view_data = {
            'model':model,
            'context_object_name':'obj',
            # these require the ModelUrlPathMixin
            'url_list_path':"%s:list"%app_path,
            'url_detail_path':"%s:detail"%app_path,
            'url_update_path':"%s:update"%app_path,
            'url_delete_path':"%s:delete"%app_path,
            'url_create_path':"%s:create"%app_path,
            'url_api_autocomplete_path':"api:%s:%sac:list"%(api_path,alternate_url_prefix),
        }

        view_data.update(**kwargs)

        # now we are concerned with specific overrides
        if not specific_view_overrides:
            specific_view_overrides={}

        # --list--
        # gather the data
        list_view_data = {
                'template_name':'duct_tape/base_list.html',
                'paginate_by':50,
                'queryset':model.objects.all(),
        }
        list_view_data.update(view_data)
        if 'list' in specific_view_overrides:
            list_view_data.update(specific_view_overrides['list'])

        # now create the view
        list_view = klass.list_view_klass.as_view(**list_view_data)
        if isinstance(list_view, (list,tuple)):
            list_view = detail_view[0]

        # --create--
        # gather the data
        create_view_data = {
                'template_name':'duct_tape/base_form.html',
        }
        create_view_data.update(view_data)
        if 'create' in specific_view_overrides:
            create_view_data.update(specific_view_overrides['create'])

        # now create the view
        create_view = klass.create_view_klass.as_view(**create_view_data), 
        if isinstance(create_view, (list,tuple)):
            create_view = create_view[0]

        # --detail--
        # gather the data
        detail_view_data = {
                'template_name':'duct_tape/base_detail.html',
        }
        detail_view_data.update(view_data)
        if 'detail' in specific_view_overrides:
            detail_view_data.update(specific_view_overrides['detail'])

        # now create the view
        # note : I use the UpdateView for detail so that there is access to the form
        #        for iterating over fields and whatnot
        detail_view = klass.update_view_klass.as_view(**detail_view_data), 
        if isinstance(detail_view, (list,tuple)):
            detail_view = detail_view[0]

        # --update--
        # gather the data
        update_view_data = {
                'template_name':'duct_tape/base_form.html',
        }
        update_view_data.update(view_data)
        if 'update' in specific_view_overrides:
            update_view_data.update(specific_view_overrides['update'])

        # now create the view
        update_view = klass.update_view_klass.as_view(**update_view_data), 
        if isinstance(update_view, (list,tuple)):
            update_view = update_view[0]

        # --delete--
        # gather the data
        delete_view_data = {
                'template_name':'duct_tape/base_confirm_delete.html',
                'success_url':'%s:list'%app_path,
        }
        delete_view_data.update(view_data)
        if 'delete' in specific_view_overrides:
            delete_view_data.delete(specific_view_overrides['delete'])

        # now create the view
        delete_view = klass.delete_view_klass.as_view(**delete_view_data), 
        if isinstance(delete_view, (list,tuple)):
            delete_view = delete_view[0]

        return patterns('',
            (r'^%s/'%alternate_url_prefix,
                include(
                    patterns('',
                        url(r'^$',list_view,name='list'),
                        url(r'^new/$',create_view,name='create'),
                        url(r'^(?P<pk>\d+)/$',detail_view,name='detail'),    
                        url(r'^(?P<pk>\d+)/update/$',update_view,name='update'),
                        url(r'^(?P<pk>\d+)/delete/$',delete_view,name='delete'),
                    ), namespace=alternate_url_prefix, app_name=alternate_url_prefix
                )
            ),
        )


