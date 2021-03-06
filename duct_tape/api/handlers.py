'''
Yanked from django, so that I could have a properly formatted message to use in a piston handler
'''
from anyjson import deserialize

from piston.utils import rc

from django.db.models.manager import Manager
from django.db.models.query import QuerySet

from piston.handler import BaseHandler
from piston.utils import rc, require_mime, require_extended, validate

from django.db.models import Q

import logging
log = logging.getLogger('console.debug')

import operator
from piston.handler import BaseHandler as PistonBaseHandler
from django.utils import simplejson

def get_object_or_404(klass,*args, **kwargs):
    """
    Uses get() to return an object, or raises a Http404 exception if the object
    does not exist.

    Note: Like with get(), an MultipleObjectsReturned will be raised if more than one
    object is found.
    """
    queryset = klass.objects.all()
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        resp = rc.NOT_FOUND
        resp.write('No %s matches the given query.' % queryset.model._meta.object_name)
        return resp

class HandlerSearchTermMixin(object):
    '''
    Usage:
    term=search_term

    This mixin allows for a term to be looked for across multiple
    search fields (as defined in the search_fields attribute of the
    overriding handler class

    Performs an 'or' filter for every search field and then distincts.
    '''
    search_fields = None
    def queryset(self, rqst, *args, **kwargs):
        queryset = super(HandlerSearchTermMixin,self).queryset(rqst, *args, **kwargs)

        if 'term' in rqst.GET:
            term = rqst.GET['term']

            # Apply keyword searches.
            def construct_search(field_name):
                if field_name.startswith('^'):
                    return "%s__istartswith" % field_name[1:]
                elif field_name.startswith('='):
                    return "%s__iexact" % field_name[1:]
                elif field_name.startswith('@'):
                    return "%s__search" % field_name[1:]
                else:
                    return "%s__icontains" % field_name

            if self.__class__.search_fields:
                or_queries = [
                    Q(**{construct_search(str(field_name)): term}) 
                        for field_name in self.search_fields]

                queryset = queryset.filter(reduce(operator.or_, or_queries))
                for field_name in self.search_fields:
                    if '__' in field_name:
                        queryset = queryset.distinct()
                        break

        return queryset

class HandlerFilterMixin(object):
    '''
    Usage:
    filter={"foo":"1234",...}

    This mixin allow you to pass a json dictionary to the
    django .filter() for this queryset
    '''
    def queryset(self, rqst, *args, **kwargs):
        queryset = super(HandlerFilterMixin,self).queryset(rqst, *args, **kwargs)
        if 'filter' in rqst.GET:
            s = rqst.GET['filter']
            data = deserialize(s)
            queryset=queryset.filter(**data)
        return queryset

class HandlerSortMixin(object):
    '''
    Usage:
    sort=[{"property":"foo","direction":"[ASC|DESC]"},...]

    This mixin allows you to pass a json structure
    to the django .order_by() for this queryset
    '''
    def queryset(self, rqst, *args, **kwargs):
        queryset = super(HandlerSortMixin,self).queryset(rqst, *args, **kwargs)
        #[{"property":"holding_id","direction":"ASC"}]
        if 'sort' in rqst.GET:
            s = rqst.GET['sort']
            data = deserialize(s)
            queryset= queryset.order_by(
                *['%s%s'%('DESC'==d['direction'] and '-' or '',d['property']) \
                        for d in data]
            )
        return queryset

class HandlerPagingMixin(object):
    def queryset(self, rqst, *args, **kwargs):
        queryset = super(HandlerPagingMixin,self).queryset(rqst, *args, **kwargs)


        self.totalCount = queryset.count() 

        if 'limit' in rqst.GET:
            limit = 25
            if 'limit' in rqst.GET:
                limit = int(rqst.GET['limit'])
            page = 1
            if 'page' in rqst.GET:
                page = int(rqst.GET['page'])

            end = limit * page

            start = 0
            if 'start' in rqst.GET:
                start = int(rqst.GET['start'])

            queryset = queryset[start:end]

        return queryset


class BaseExtHandler(
        HandlerPagingMixin,
        HandlerSortMixin,
        HandlerFilterMixin,
        HandlerSearchTermMixin,
        PistonBaseHandler):

    def get_object(self,*args, **kwargs):
        rslt = get_object_or_404(self.model,*args,**kwargs)
        return rslt 

    #TODO : name this something different and move the list making somewhere else
    def queryset(self, rqst, *args, **kwargs):
        """
        Uses filter() to return a list of objects, or raise a Http404 exception if
        the list is empty.

        """
        queryset = super(BaseExtHandler,self).queryset(rqst, *args, **kwargs)
        if not hasattr(self,'totalCount'):
            self.totalCount = queryset.count()
        return (self.totalCount,queryset)

    def read(self,rqst,id=None):
        log.debug('READ')
        log.debug(id)
        # on GET
        if id:
            return self.get_object(pk=id)
        else:
            totalCount,queryset = self.queryset(rqst)
            obj_list = [obj for obj in queryset]
            if not obj_list:
                resp = rc.NOT_FOUND
                resp.write('No %s matches the given query.' % queryset.model._meta.object_name)
                return resp

            return (totalCount,obj_list)      

    def create(self, rqst, *args, **kwargs):
        log.debug('CREATE')
        if not self.has_model():
            return rc.NOT_IMPLEMENTED
        
        attrs = self.flatten_dict(rqst.POST)
        if attrs.has_key('data'):
            ext_posted_data = simplejson.loads(rqst.POST.get('data'))
            attrs = self.flatten_dict(ext_posted_data)        
        
        try:
            inst = self.model.objects.get(**attrs)
            return rc.DUPLICATE_ENTRY
        except self.model.DoesNotExist:
            inst = self.model(**attrs)
            inst.save()
            return inst
        except self.model.MultipleObjectsReturned:
            return rc.DUPLICATE_ENTRY
    
    def update(self, rqst, id):
        log.debug('UPDATE')
        if not self.has_model():
            log.debug('rc.NOT_IMPLEMENTED')
            return rc.NOT_IMPLEMENTED
    
        data = deserialize(rqst.raw_post_data)
        attrs = self.flatten_dict(data)
    
        inst = self.model.objects.get(id=id)
        for k,v in attrs.iteritems():
            setattr( inst, k, v )

        inst.save()
        
        return inst

    def delete(self,rqst,*args,**kwargs):
        # on DELETE
        return super(BaseExtHandler,self).delete(rqst,*args,**kwargs)

class BaseAutoCompleteHandler(
        HandlerSearchTermMixin,
        PistonBaseHandler):
    '''
    This is only meant for reads for the autocompleters
    (until I switch everything out for ext)
    '''
        
    def get_value_and_label(self,obj):
        return {'label':str(obj),
                 'value':obj.pk}

    def read(self,rqst,*args,**kwargs):
        queryset = self.queryset(rqst,*args,**kwargs)
        obj_list = [self.get_value_and_label(obj) for obj in queryset]
        return obj_list      

