import requests
from requests.auth import HTTPBasicAuth
import json
import logging
logging.basicConfig(level=logging.DEBUG)


class ScrumwiseObject(object):
    _object_type = None

    def __init__(self, scrumwise_session, data=None):
        self.scrumwise_session = scrumwise_session
        self.obj_id = None
        if data is not None:
            self.update_object_by_data(data)

    @property
    def id(self):
        return self.obj_id

    @property
    def is_initialised(self):
        return self.id is not None

    def update_object_by_data(self, data):
        self.obj_id = self.get_id_of_item(data)
        if self.id is None:
            raise Exception('Bad Type')
        return True

    @classmethod
    def have_good_type(cls, object_type):
        return object_type.get('objectType') == cls._object_type

    @classmethod
    def get_id_of_item(cls, item):
        return item.get('id') if cls.have_good_type(item) else None

    def __str__(self):
        if self.is_initialised:
            return '{object_type}: {id}'.format(object_type=self._object_type, id=self.id)
        else:
            return '{class_name} is not initialised'.format(class_name=self.__class__)

    def __repr__(self):
        return str(self)


class ScrumwiseObjectList(dict):
    _element_class = None

    def __init__(self, scrumwise_session, **kwargs):
        self.scrumwise_session = scrumwise_session
        dict.__init__(self, kwargs)

    @property
    def ids(self):
        return self.keys()

    @property
    def names(self):
        return [self[_id].name for _id in self.ids]

    def update_object_by_data(self, data):
        if not isinstance(data, list) or data is None:
            return False

        for item in data:
            if not self.try_update_one_object_by_data(item):
                element = self._element_class(self.scrumwise_session)
                element_id = element.get_id_of_item(item)
                self.update({element_id: element})
                self[element_id].update_object_by_data(item)
        return True

    def try_update_one_object_by_data(self, item):
        id_item = self._element_class.get_id_of_item(item)
        if id_item is None:
            return False
        element = self.get(id_item)
        if element is None:
            return False
        return element.update_object_by_data(item)

    def by_id(self, obj_id):
        return self.get(obj_id)

    def by_name(self, name):
        return self.by_attr('name', name)

    def by_attr(self, attr, value):
        if isinstance(value, list):
            sub = self.__class__(self.scrumwise_session)
            sub.update({obj_id: data for v in value for obj_id, data in self.items() if v == getattr(data, attr)})
            return sub
        for elem in self.values():
            if value == getattr(elem, attr):
                return elem
        return None


class ScrumwiseData(ScrumwiseObject):
    _object_type = 'Data'

    def __init__(self, scrumwise_session):
        super(ScrumwiseData, self).__init__(scrumwise_session)
        self.projects = ScrumwiseProjectList(self.scrumwise_session)
        self.persons = None
        self.deleted_persons = None

    def update_object_by_data(self, data):
        self.have_good_type(data)
        self.persons = data.get('persons')
        self.deleted_persons = data.get('deletedPersons')
        self.projects.update_object_by_data(data.get('projects'))
        return True


class ScrumwisePy(ScrumwiseData):
    _object_type = 'Data'

    def __init__(self, host, port, username, key):
        self._revision = None
        self.host = host
        self.port = port
        self.username = username
        self.key = key
        self.scrumwise_data = ScrumwiseGetData(self)
        self.last_data_version = 0
        self.requests_api = ScrumwiseRequests()
        super(ScrumwisePy, self).__init__(self)

    @property
    def baseurl(self):
        return "https://{host}:{port}".format(host=self.host, port=self.port)

    @property
    def requests_auth(self):
        return HTTPBasicAuth(self.username, self.key)

    @property
    def data(self):
        return self.scrumwise_data.data

    @property
    def result(self):
        return self.data.get('result')

    def update_data_version(self, version):
        if version is not None:
            self.last_data_version = version
            return True
        return False

    def open(self):
        return self.update_data()

    def update_data(self):
        return self.scrumwise_data.request_api() and self.update_object_by_data(self.result)

    def append_requests(self, scrumwise_requests):
        self.requests_api.append(scrumwise_requests)

    def clear_requests(self):
        self.requests_api.clear()

    def exec_request_api(self):
        self.requests_api.request_api()
        self.clear_requests()
        return self.update_data()


class ScrumwiseProject(ScrumwiseObject):
    _object_type = 'Project'

    def __init__(self, scrumwise_session):
        super(ScrumwiseProject, self).__init__(scrumwise_session)
        self.backlog_items = ScrumwiseBacklogItemList(self.scrumwise_session)
        self.tags = ScrumwiseTagList(self.scrumwise_session)
        self.externalID = self.name = self.description = self.link = self.status = self.roughEstimateUnit = None
        self.detailedEstimateUnit = self.timeTrackingUnit = None

    def update_object_by_data(self, data):
        super(ScrumwiseProject, self).update_object_by_data(data)
        self.externalID = data.get('externalID')
        self.name = data.get('name')
        self.description = data.get('description')
        self.link = data.get('link')
        self.status = data.get('status')
        self.roughEstimateUnit = data.get('roughEstimateUnit')
        self.detailedEstimateUnit = data.get('detailedEstimateUnit')
        self.timeTrackingUnit = data.get('timeTrackingUnit')
        self.tags.update_object_by_data(data.get('tags'))
        self.backlog_items.update_object_by_data(data.get('backlogItems'))
        return True

    def add_tag(self, name, color=None, description=None):
        self.scrumwise_session.append_requests(ScrumwiseAddTagRequest(
            self.scrumwise_session, project_id=self.id, name=name, color=color, description=description)
        )
        return self


class ScrumwiseProjectList(ScrumwiseObjectList):
    _element_class = ScrumwiseProject


class ScrumwiseBacklogItem(ScrumwiseObject):
    _object_type = 'BacklogItem'

    def __init__(self, scrumwise_session):
        super(ScrumwiseBacklogItem, self).__init__(scrumwise_session)
        self.tasks = ScrumwiseTaskList(self.scrumwise_session)
        self.externalID = self.name = self.description = self.link = self.status = None
        self.project_id = self.item_number = None

    def update_object_by_data(self, data):
        super(ScrumwiseBacklogItem, self).update_object_by_data(data)
        self.externalID = data.get('externalID')
        self.name = data.get('name')
        self.description = data.get('description')
        self.link = data.get('link')
        self.status = data.get('status')
        self.project_id = data.get('projectID')
        self.item_number = data.get('itemNumber')
        self.tasks.update_object_by_data(data.get('tasks'))
        return True

    def have_task_by_name(self, name):
        return self.tasks.by_name(name) is not None

    def create_task_by_name(self, name, description):
        task_requests = ScrumwiseRequests()
        task = self.tasks.by_name(name)

        if task is None:
            task_requests.append(ScrumwiseAddTaskRequest(self.scrumwise_session, self.id, name, description))
        else:
            raise Exception('Task {name} exist'.format(name=name))

        self.scrumwise_session.append_requests(task_requests)
        return self

    def update_task_by_name(self, name, description):
        task_requests = ScrumwiseRequests()
        task = self.tasks.by_name(name)

        if task is None:
            raise Exception('Task {name} does not exist'.format(name=name))
        else:
            task_requests.append(ScrumwiseSetTaskDescriptionRequest(self.scrumwise_session, task.id, description))

        self.scrumwise_session.append_requests(task_requests)
        return self


class ScrumwiseBacklogItemList(ScrumwiseObjectList):
    _element_class = ScrumwiseBacklogItem

    def by_item_number(self, item_number: int):
        return self.by_attr('item_number', item_number)


class ScrumwiseTask(ScrumwiseObject):
    _object_type = 'Task'

    def __init__(self, scrumwise_session, data=None):
        super(ScrumwiseTask, self).__init__(scrumwise_session, data)
        self.externalID = self.name = self.description = self.link = self.status = None
        self.project_id = self.backlog_item_id = self.tag_ids = None

    @property
    def tags(self):
        return self.scrumwise_session.projects.by_id(self.project_id).tags.by_id(self.tag_ids)

    def update_object_by_data(self, data):
        super(ScrumwiseTask, self).update_object_by_data(data)
        self.externalID = data.get('externalID')
        self.name = data.get('name')
        self.description = data.get('description')
        self.link = data.get('link')
        self.status = data.get('status')
        self.project_id = data.get('projectID')
        self.backlog_item_id = data.get('backlogItemID')
        self.tag_ids = data.get('tagIDs')
        return True

    def get_tags_which_are_present_without_name(self, tags_name):
        if not isinstance(tags_name, list):
            tags_name = [tags_name]

        present_tags = self.tag_ids
        tags_id = self.scrumwise_session.projects.by_id(self.project_id).tags.by_name(tags_name).ids
        return [t for t in present_tags if t not in tags_id]

    def get_tags_which_are_not_present(self, tags_name):
        if not isinstance(tags_name, list):
            tags_name = [tags_name]

        present_tags = self.tag_ids
        tags_id = self.scrumwise_session.projects.by_id(self.project_id).tags.by_name(tags_name).ids
        return [t for t in tags_id if t not in present_tags]

    def clean_all_tags_except(self, tags_name):
        if not isinstance(tags_name, list):
            tags_name = [tags_name]

        tags_to_remove = self.get_tags_which_are_present_without_name(tags_name)

        tag_requests = ScrumwiseRequests()
        for tag_id in tags_to_remove:
            tag_requests.append(ScrumwiseRemoveTagFromObjectRequest(self.scrumwise_session, tag_id, 'Task', self.id))

        self.scrumwise_session.append_requests(tag_requests)

        return self

    def set_tags_on_task(self, tags_name):
        if not isinstance(tags_name, list):
            tags_name = [tags_name]

        scrumwise_project = self.scrumwise_session.projects.by_id(self.project_id)

        tags_to_append = self.get_tags_which_are_not_present(tags_name)

        tag_requests = ScrumwiseRequests()
        for tag_id in tags_to_append:
            tag_name = scrumwise_project.tags.by_id(tag_id).name
            if tag_name is not None:
                tag_requests.append(ScrumwiseAddTagOnObjectRequest(self.scrumwise_session, tag_id, 'Task', self.id))

        self.scrumwise_session.append_requests(tag_requests)
        return self


class ScrumwiseTaskList(ScrumwiseObjectList):
    _element_class = ScrumwiseTask


class ScrumwiseTag(ScrumwiseObject):
    _object_type = 'Tag'

    def __init__(self, scrumwise_session, data=None):
        super(ScrumwiseTag, self).__init__(scrumwise_session, data)
        self.externalID = self.name = self.description = self.status = self.project_id = None

    def update_object_by_data(self, data):
        super(ScrumwiseTag, self).update_object_by_data(data)
        self.externalID = data.get('externalID')
        self.name = data.get('name')
        self.description = data.get('description')
        self.status = data.get('status')
        self.project_id = data.get('projectID')
        return True


class ScrumwiseTagList(ScrumwiseObjectList):
    _element_class = ScrumwiseTag


class ScrumwiseRequest(object):
    _url_path = ''
    _include_data_in_request = ''

    def __init__(self, scrumwisepy):
        self._request_params = dict()
        self.scrumwisepy = scrumwisepy
        self.requests_responce = None

    @property
    def url(self):
        return "{url}/{url_path}".format(url=self.scrumwisepy.baseurl, url_path=self._url_path)

    @property
    def data_raw(self):
        return self.requests_responce.text

    @property
    def data(self):
        return json.loads(self.data_raw)

    @property
    def data_version(self):
        return self.data.get('dataVersion')

    @property
    def _request_data(self):
        return self._request_params

    def request_api(self, required_data_version=False):
        if required_data_version:
            self._request_params['requiredDataVersion'] = self.scrumwisepy.last_data_version
        self.requests_responce = requests.get(self.url, auth=self.scrumwisepy.requests_auth, params=self._request_data)
        return self.scrumwisepy.update_data_version(self.data_version) and self.check_request()

    def check_request(self):
        return self.requests_responce is not None and self.requests_responce.status_code == requests.codes.ok


class ScrumwiseRequests(list):
    """A container for manipulating lists of hosts"""

    def append(self, obj):
        if isinstance(obj, list):
            for o in obj:
                self.append(o)
        else:
            super(ScrumwiseRequests, self).append(obj)

    def request_api(self, required_data_version=False):
        for request in self:
            if not request.request_api(required_data_version):
                raise Exception("Error to execute {request}".format(request=request))

        return True


class ScrumwiseGetData(ScrumwiseRequest):
    _url_path = 'service/api/v1/getData'

    def __init__(self, *args):
        super(ScrumwiseGetData, self).__init__(*args)
        self._request_params = dict(includeProperties="Project.backlogItems,BacklogItem.tasks,Project.tags")


class ScrumwiseAddTaskRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/addTask'

    def __init__(self, scrumwisepy, backlog_id, name, description):
        super(ScrumwiseAddTaskRequest, self).__init__(scrumwisepy)
        self._request_params['name'] = name
        self._request_params['description'] = description
        self._request_params['backlogItemID'] = backlog_id
        self._request_params['estimate'] = -1


class ScrumwiseSetTaskDescriptionRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/setTaskDescription'

    def __init__(self, scrumwisepy, task_id, description):
        super(ScrumwiseSetTaskDescriptionRequest, self).__init__(scrumwisepy)
        self._request_params['taskID'] = task_id
        self._request_params['description'] = description


class ScrumwiseAddTagOnObjectRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/addTagOnObject'

    def __init__(self, scrumwisepy, tag_id, object_type, object_id):
        super(ScrumwiseAddTagOnObjectRequest, self).__init__(scrumwisepy)
        self._request_params['tagID'] = tag_id
        self._request_params['objectType'] = object_type
        self._request_params['objectID'] = object_id


class ScrumwiseRemoveTagFromObjectRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/removeTagFromObject'

    def __init__(self, scrumwisepy, tag_id, object_type, object_id):
        super(ScrumwiseRemoveTagFromObjectRequest, self).__init__(scrumwisepy)
        self._request_params['tagID'] = tag_id
        self._request_params['objectType'] = object_type
        self._request_params['objectID'] = object_id


class ScrumwiseAddTagRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/addTag'

    def __init__(self, scrumwisepy, project_id, name, description=None, color=None, index=-1, external_id=None):
        super(ScrumwiseAddTagRequest, self).__init__(scrumwisepy)
        self._request_params['projectID'] = project_id
        self._request_params['externalID'] = external_id
        self._request_params['name'] = name
        self._request_params['description'] = description
        self._request_params['color'] = color
        self._request_params['index'] = index


class ScrumwiseDeleteTagRequest(ScrumwiseRequest):
    _url_path = 'service/api/v1/addTag'

    def __init__(self, scrumwisepy, tag_id, external_id=None):
        super(ScrumwiseDeleteTagRequest, self).__init__(scrumwisepy)
        self._request_params['tagID'] = tag_id
        self._request_params['externalID'] = external_id
