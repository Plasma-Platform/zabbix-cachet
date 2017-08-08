import json
import requests
import sys
import logging
from operator import itemgetter


def client_http_error(url, code, message):
    """Logging HTTP errors
    """
    logging.error('ClientHttpError[%s, %s: %s]' % (url, code, message))
    sys.exit(1)


class Cachet:
    def __init__(self, server, token, verify=True):
        """Init Cachet class for further needs

        : param server: string
        :param token: string
        :return: object
        """
        self.server = server + '/api/v1/'
        self.token = token
        self.headers = {
            'X-Cachet-Token': self.token,
            'Accept': 'application/json; indent=4'
        }
        self.verify = verify

    def _http_error(url, code, message):
        """Print error message and exit if has request errors
        """
        logging.error('ClientHttpError[%s, %s: %s]' % (url, code, message))
        sys.exit(1)

    def _http_post(self, url, params):
        """Make POST and return json response

        :param url: str
        :param params: dict
        :return: json
        """
        url = self.server + url
        try:
            r = requests.post(
                url=url,
                data=params,
                headers=self.headers,
                verify=self.verify
            )
        except requests.exceptions.RequestException as e:
            raise self._http_error(url, None, e)
        # r.raise_for_status()
        if r.status_code != 200:
            return self._http_error(url, r.status_code, r.text)
        data = json.loads(r.text)
        # TODO: check data
        return data

    def _http_get(self, url, params=None):
        """
        Helper for HTTP GET request
        :param: url: str
        :param: params:
        :return: json data
        """
        if params is None:
            params = {}
        url = self.server + url
        try:
            r = requests.get(
                url=url,
                headers=self.headers,
                params=params,
                verify=self.verify
            )
        except requests.exceptions.RequestException as e:
            raise client_http_error(url, None, e)
        # r.raise_for_status()
        if r.status_code != 200:
            return client_http_error(url, r.status_code,
                                     json.loads(r.text)['errors'])
        data = json.loads(r.text)
        # TODO: check data
        return data

    def _http_put(self, url, params):
        """
        Make PUT and return json response
        :param url: str
        :param params: dict
        :return: json
        """
        url = self.server + url
        try:
            r = requests.put(
                url=url,
                json=params,
                headers=self.headers,
                verify=self.verify
            )
        except requests.exceptions.RequestException as e:
            raise client_http_error(url, None, e)
        # r.raise_for_status()
        if r.status_code != 200:
            return client_http_error(url, r.status_code, r.text)
        data = json.loads(r.text)
        # TODO: check data
        return data

    def get_component(self, id):
        """
        Get component params based its id
        @param id: string
        @return: dict
        """
        url = 'components/' + str(id)
        data = self._http_get(url)
        return data

    def get_components(self, name=None):
        """
        Get all registered components or return a component details
        if name specified
        @param name: string
        @return: dict of data or list
        """
        url = 'components'
        data = self._http_get(url)
        if name:
            components = {'data': []}
            for component in data['data']:
                if component['name'] == name:
                    components['data'].append(component)
            if len(components['data']) < 1:
                return {'id': 0, 'name': 'Does not exists'}
            elif len(components['data']) == 1:
                return components['data'][0]
        return data

    def new_components(self, name, **kwargs):
        """
        Create new components
        @param name: string
        @param kwargs: various additional values =)
        @return: dict of data
        """
        # Get values for new component
        params = {
            'name': name,
            'link': '',
            'description': '',
            'status': '1',
            'group_id': 0
        }
        params.update(kwargs)
        # Check if components with same name already exists in same group
        component = self.get_components(name)
        # There are more that one component with same name already
        if 'data' in component:
            for i in component['data']:
                if i['group_id'] == params['group_id']:
                    return i
            else:
                component = {'id': 0}

        # Create component if it does not exist or exist in other group
        if component['id'] == 0 or component['group_id'] != params['group_id']:
            url = 'components'

            logging.debug(
                'Creating Cachet component {name}...'.format(
                    name=params['name']
                )
            )
            data = self._http_post(url, params)
            logging.info(
                'Component {name} was created in group id {group_id}.'.format(
                    name=params['name'],
                    group_id=data['data']['group_id']
                )
            )
            return data['data']
        else:
            return component

    def upd_components(self, id, **kwargs):
        """
        Update component
        @param id: string
        @param kwargs: various additional values =)
        @return: boolean
        """
        url = 'components/' + str(id)
        params = self.get_component(id)['data']
        params.update(kwargs)
        data = self._http_put(url, params)
        logging.info(
            'Component {name} (id={id}) was updated. Status - {status}'.format(
                name=data['data']['name'],
                id=id,
                status=data['data']['status_name'])
        )
        return data

    def get_components_gr(self, name=None):
        """
        Get all registered components group or return a component group
        details if name specified
        @param name: string
        @return: dict of data
        """
        url = 'components/groups'
        data = self._http_get(url)
        if name:
            for group in data['data']:
                if group['name'] == name:
                    return group
            else:
                return {'id': 0, 'name': 'Does not exists'}
        return data

    def new_components_gr(self, name):
        """
        Create new components group
        @param name: string
        @return: dict of data
        """
        # Check if component's group already exists
        componenets_gr_id = self.get_components_gr(name)
        if componenets_gr_id['id'] == 0:
            url = 'components/groups'
            # TODO: make if possible to configure default collapsed value
            params = {'name': name, 'collapsed': 2}
            logging.debug(
                'Creating Component Group {}...'.format(params['name'])
            )
            data = self._http_post(url, params)
            logging.info(
                'Component Group {} was created.'.format(params['name'])
            )
            return data['data']
        else:
            return componenets_gr_id

    def get_incident(self, component_id):
        """
        Get last incident for component_id
        @param component_id: string
        @return: dict of data
        """
        # TODO: make search by name
        url = 'incidents'
        data = self._http_get(url)
        total_pages = int(data['meta']['pagination']['total_pages'])
        for page in range(total_pages, 0, -1):
            data = self._http_get(url, params={'page': page})
            data_sorted = sorted(
                data['data'],
                key=itemgetter('id'),
                reverse=True
            )
            for incident in data_sorted:
                if str(incident['component_id']) == str(component_id):
                    # Convert status to str
                    incident['status'] = str(incident['status'])
                    return incident
        return {'id': '0', 'name': 'Does not exist', 'status': '-1'}

    def new_incidents(self, **kwargs):
        """
        Create a new incident.
        @param kwargs: various additional values =)
                        name, message, status,
                        component_id, component_status
        @return: dict of data
        """
        params = {'visible': 1, 'notify': 'true'}
        url = 'incidents'
        params.update(kwargs)
        data = self._http_post(url, params)
        logging.info('Incident {name} (id={incident_id}) was created for'
                     'component id {component_id}.'.format(
                        name=params['name'],
                        incident_id=data['data']['id'],
                        component_id=params['component_id']
        ))
        return data['data']

    def upd_incident(self, id, **kwargs):
        """
        Update incident
        @param id: string
        @param kwargs: various additional values =)
                message, status,
                component_status
        @return: boolean
        """
        url = 'incidents/' + str(id)
        params = kwargs
        data = self._http_put(url, params)
        logging.info('Incident ID {id} was updated. Status - {status}.'.format(
            id=id,
            status=data['data']['human_status'])
        )
        return data

    def get_metrics(self):
        url = 'metrics'
        response = self._http_get(url)
        pag_info = response['meta']['pagination']

        # If we didn't get all objects - try again
        if pag_info['total_pages'] > 1:
            # Get objects from a big pagination page
            return self._http_get(url, {'per_page': pag_info['total']})['data']

        return response['data']

    def create_metrics(self, **kwargs):
        url = 'metrics'
        params = {'default_value': 0}
        params.update(kwargs)

        data = self._http_post(url, params)
        logging.info("A new metric '{name}' was created".format(
            name=params['name']
        ))

        return data

    def add_point_to_metric(self, id, value, timestamp):
        url = 'metrics/{id}/points'.format(id=id)
        params = {
            'value': value,
            'timestamp': timestamp
        }

        data = self._http_post(url, params)
        return data

