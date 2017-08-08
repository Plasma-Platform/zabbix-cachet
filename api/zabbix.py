import requests

from pyzabbix import ZabbixAPI


class Zabbix:
    def __init__(self, server, user, password, verify=True):
        """Init Zabbix class for further needs

        :param user: string
        :param password: string
        :return: pyzabbix object
        """
        self.server = server
        self.user = user
        self.password = password

        # Enable HTTP auth
        session = requests.Session()
        session.auth = (user, password)

        self.zapi = ZabbixAPI(server, session)
        self.zapi.session.verify = verify
        self.zapi.login(user, password)

    def get_trigger(self, triggerid):
        """Get trigger information

        @param triggerid: string
        @return: dict of data
        """
        trigger = self.zapi.trigger.get(
            expandComment='true',
            expandDescription='true',
            triggerids=triggerid)
        return trigger[0]

    def get_event(self, triggerid):
        """Get event information based on triggerid

        @param triggerid: string
        @return: dict of data
        """
        zbx_event = self.zapi.event.get(
            select_acknowledges='extend',
            expandDescription='true',
            object=0,
            value=1,
            objectids=triggerid)
        if len(zbx_event) > 1:
            return zbx_event[-1]
        return zbx_event

    def get_itservice_by_name(self, trigger_name):
        """Get IT Service by name

        Args:
            trigger_name (String): Name of service

        Returns:
            Dict: IT Service object
        """
        service = self.zapi.service.get(
            filter={'name': trigger_name}
        )
        try:
            return service[0]
        except IndexError:
            return {}

    def get_itservices(self, root=None):
        """
        Return tree of Zabbix IT Services
        root (hidden)
           - service1 (Cachet componentgroup)
             - child_service1 (Cachet component)
             - child_service2 (Cachet component)
           - service2 (Cachet componentgroup)
             - child_service3 (Cachet component)
        :param root: Name of service that will be root of tree.
                    Actually it will not be present in return tree.
                    It's using just as a start point , string
        :return: Tree of Zabbix IT Services, List
        """
        if root:
            root_service = self.zapi.service.get(
                selectDependencies='extend',
                filter={'name': root}
            )
            try:
                root_service = root_service[0]
            except:
                logging.error(
                    'Can not find "{}" service'
                    'in Zabbix'.format(root)
                )
                sys.exit(1)
            service_ids = []
            for dependency in root_service['dependencies']:
                service_ids.append(dependency['serviceid'])
            services = self.zapi.service.get(
                selectDependencies='extend',
                serviceids=service_ids)
        else:
            services = self.zapi.service.get(
                selectDependencies='extend',
                output='extend')
        if not services:
            logging.error(
                'Can not find any child service for "{}"'.format(root)
            )
            return []
        for idx, service in enumerate(services):
            child_services = []
            for dependency in service['dependencies']:
                child_services.append(dependency['serviceid'])
            child_services = self.zapi.service.get(
                    selectDependencies='extend',
                    serviceids=child_services)
            services[idx]['dependencies'] = child_services
        return services

    def get_sla(self, serviceids, time_from, time_to):
        """Get services SLA in current time interval

        Args:
            serviceids (list): Id's of services
            time_from (float): Start timestamp interval
            time_to (float): End timestamp interval
        Returns:
            dict: object with info about SLA time
        """
        result = self.zapi.service.getsla(
            serviceids=serviceids,
            intervals={
                'from': time_from,
                'to': time_to
            }
        )
        return result
