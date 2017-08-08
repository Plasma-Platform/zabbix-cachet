#!/usr/bin/env python3
"""
This script populated Cachet of Zabbix IT Services
"""
import sys
import os
import datetime
import time
import threading
import logging
import yaml

from api.zabbix import Zabbix
from api.cachet import Cachet

__author__ = 'Artem Alexandrov <qk4l()tem4uk.ru>'
__license__ = """The MIT License (MIT)"""
__version__ = '0.2'


# Templates for incident displaying
MESSAGING_TMPL = \
    "{message}\n\n###### {ack_time} by {author}\n\n______\n"
INVESTIGATING_TMPL = \
    "{group} | {component} check **failed** - {time}\n\n```{description}```"
RESOLVING_TMPL = \
    "__Resolved__ - {time}\n\n______\n"


def triggers_watcher(service_map):
    """
    Check zabbix triggers and update Cachet components
    Zabbix Priority:
        0 - (default) not classified;
        1 - information;
        2 - warning;
        3 - average;
        4 - high;
        5 - disaster.
    Cachet Incident Statuses:
        0 - Scheduled - This status is used for a scheduled status.
        1 - Investigating - You have reports of a problem and you're currently
            looking into them.
        2 - Identified - You've found the issue and you're working on a fix.
        3 - Watching - You've since deployed a fix and you're currently
            watching the situation.
        4 - Fixed
    @param service_map: list of tuples
    @return: boolean
    """
    # TODO: This function needs to be refactored
    for i in service_map:
        # inc_status = 1
        # comp_status = 1
        # inc_name = ''
        inc_msg = ''

        if 'triggerid' in i:
            trigger = zapi.get_trigger(i['triggerid'])
            # Check if incident already registered
            # Trigger non Active
            if str(trigger['value']) == '0':
                component_status = \
                    cachet.get_component(i['component_id'])['data']['status']
                # And component in operational mode
                if str(component_status) == '1':
                    continue
                else:
                    # And component not operational mode
                    last_inc = cachet.get_incident(i['component_id'])
                    if str(last_inc['id']) != '0':
                        inc_msg = RESOLVING_TMPL.format(
                            time=datetime.datetime.now()
                                .strftime('%b %d, %H:%M'),
                        ) + cachet.get_incident(i['component_id'])['message']
                        cachet.upd_incident(
                            last_inc['id'],
                            status=4,
                            component_id=i['component_id'],
                            component_status=1,
                            message=inc_msg
                        )
                    # Incident does not exist. Just change component status
                    else:
                        cachet.upd_components(i['component_id'], status=1)
                    continue

            # Trigger in Active state
            elif trigger['value'] == '1':
                zbx_event = zapi.get_event(i['triggerid'])
                inc_name = trigger['description']
                if zbx_event['acknowledged'] == '1':
                    inc_status = 2
                    inc_msg = cachet.get_incident(i['component_id'])['message']
                    for msg in zbx_event['acknowledges']:
                        ack_time = datetime.datetime.fromtimestamp(
                            int(msg['clock'])
                        ).strftime('%b %d, %H:%M')

                        ack_msg = MESSAGING_TMPL.format(
                            message=msg['message'],
                            ack_time=ack_time,
                            author = msg['name'] + ' ' + msg['surname']
                        )
                        if ack_msg not in inc_msg:
                            inc_msg = ack_msg + inc_msg

                else:
                    inc_status = 1
                if int(trigger['priority']) >= 4:
                    comp_status = 4
                elif int(trigger['priority']) == 3:
                    comp_status = 3
                else:
                    comp_status = 2

                # if not inc_msg and trigger['comments']:
                #     inc_msg = trigger['comments']
                if not inc_msg:
                    inc_msg = INVESTIGATING_TMPL.format(
                        group=i['group_name'],
                        component=i['component_name'],
                        time=datetime.datetime.now()
                            .strftime('%b %d, %H:%M'),
                        description=trigger['description'],
                    )
                if 'group_name' in i:
                    inc_name = i['group_name'] + ' | ' + inc_name

                last_inc = cachet.get_incident(i['component_id'])
                # Incident not registered
                if last_inc['status'] in ('-1', '4'):
                    cachet.new_incidents(
                        name=inc_name,
                        message=inc_msg,
                        status=inc_status,
                        component_id=i['component_id'],
                        component_status=comp_status,
                    )

                # Incident already registered
                elif last_inc['status'] not in ('-1', '4'):
                    # Only incident message can change.
                    # So check if this have happened
                    if last_inc['message'].strip() != inc_msg.strip():
                        cachet.upd_incident(
                            last_inc['id'],
                            status=inc_status,
                            component_status=comp_status,
                            message=inc_msg
                        )

        else:
            # TODO: ServiceID
            inc_msg = 'TODO: ServiceID'
            continue

    return True


def triggers_watcher_worker(service_map, interval, e):
    """
    Worker for triggers_watcher. Run it continuously with specific interval
    @param service_map: list of tuples
    @param interval: interval in seconds
    @param e: treading.Event object
    @return:
    """
    logging.info('start trigger watcher')
    while not e.is_set():
        logging.debug('check Zabbix triggers')
        triggers_watcher(service_map)
        time.sleep(interval)
    logging.info('end trigger watcher')


def metrics_updater(metrics_mapping, interval):
    # Get SLA of current services
    service_ids = [service['service_id'] for service in metrics_mapping]
    time_to = time.mktime(datetime.datetime.now().timetuple())
    time_from = time_to - interval

    result = zapi.get_sla(service_ids, time_from, time_to)

    for service in metrics_mapping:
        # Get SLA info
        sla_info = result[service['service_id']]['sla'][0]

        # Send as point in Cachet metric
        cachet.add_point_to_metric(
            id=service['metric_id'],
            value=sla_info['sla'],
            timestamp=sla_info['to']
        )

    logging.info("SLA was updated.")

def metrics_updater_worker(metrics_mapping, interval):
    logging.info('Start metrics updater')
    while True:
        logging.debug('Getting SLA of Zabbix services and send to Cachet')
        metrics_updater(metrics_mapping, interval)
        time.sleep(interval)


def init_metrics(service_names):
    """Create a mapping array between Zabbix services and Cachet metrics

    Args:
        service_names (list): list of service names
    Returns:
        list: List of dicts which assign for every service own metric
    """

    # List of services that should be tracked
    services = []
    for name in service_names:
        service = zapi.get_itservice_by_name(name)
        if service:
            services.append(service)
        elif service and service['showsla'] == '0':
            logging.error("Zabbix service with name '{name}' does not setting "
                          "up to show SLA.".format(name=name))
        else:
            logging.error("Zabbix service with name '{name}' does not found! "
                          "Please, check your config"
                          .format(name=name))

    # List of all metrics
    metrics = cachet.get_metrics()

    metrics_mapping = []
    for service in services:
        result = list(filter(
            lambda x: service['name'] + ' Uptime' == x['name'],
            metrics
        ))

        # If metric was found for current service - choose it
        if result:
            result = result[0]
        # if not - create a new metric
        else:
            result = cachet.create_metrics(
                name='{service} Uptime'.format(service=service['name']),
                description= 'Uptime chart for {service} service'.format(
                    service = service['name']
                ),
                suffix='Percent',
                default_value=0,
            )['data']

        metrics_mapping.append({
            'service_id': service['serviceid'],
            'metric_id': result['id']
        })

    return metrics_mapping

def init_cachet(services):
    """
    Init Cachet by syncing Zabbix service to it
    Also func create mapping batten Cachet components and Zabbix IT services
    @param services: list
    @return: list of tuples
    """
    # Zabbix Triggers to Cachet components id map
    data = []
    for zbx_service in services:
        # Check if zbx_service has childes
        zxb2cachet_i = {}
        if zbx_service['dependencies']:
            group = cachet.new_components_gr(zbx_service['name'])
            for dependency in zbx_service['dependencies']:
                # Component without trigger
                if int(dependency['triggerid']) != 0:
                    trigger = zapi.get_trigger(dependency['triggerid'])
                    component = cachet.new_components(
                        dependency['name'],
                        group_id=group['id'],
                        link=trigger['url'],
                        description=trigger['description']
                    )
                    # Create a map of Zabbix Trigger <> Cachet IDs
                    zxb2cachet_i = {'triggerid': dependency['triggerid']}
                else:
                    component = cachet.new_components(
                        dependency['name'],
                        group_id=group['id']
                    )
                    zxb2cachet_i = {'serviceid': dependency['serviceid']}

                zxb2cachet_i.update({
                    'group_id': group['id'],
                    'group_name': group['name'],
                    'component_id': component['id'],
                    'component_name': component['name']
                })
                data.append(zxb2cachet_i)
        else:
            # Component with trigger
            if zbx_service['triggerid']:
                if int(zbx_service['triggerid']) == 0:
                    logging.debug("Zabbix Service with service name = '{}' "
                                  " does not have trigger or child service"
                                  .format(zbx_service['serviceid'])
                                  )
                    continue
                trigger = zapi.get_trigger(zbx_service['triggerid'])
                component = cachet.new_components(
                    zbx_service['name'],
                    link=trigger['url'],
                    description=trigger['description']
                )
                # Create a map of Zabbix Trigger <> Cachet IDs
                zxb2cachet_i = {'triggerid': zbx_service['triggerid'],
                                'component_id': component['id'],
                                'component_name': component['name']}
            data.append(zxb2cachet_i)
    return data


def read_config(config_f):
    """
    Read config file
    @param config_f: strung
    @return: dict of data
    """
    config = yaml.load(open(config_f, "r"))
    return config


if __name__ == '__main__':
    # Getting congig file
    if os.getenv('CONFIG_FILE') is not None:
        CONFIG_F = os.environ['CONFIG_FILE']
    else:
        CONFIG_F = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
    config = read_config(CONFIG_F)

    ZABBIX = config['zabbix']
    CACHET = config['cachet']
    SETTINGS = config['settings']
    exit_status = 0

    # Set Logging
    log_level = logging.getLevelName(SETTINGS['log_level'])
    log_level_requests = logging.getLevelName(SETTINGS['log_level_requests'])
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s: (%(threadName)s) %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %Z'
    )
    logging.getLogger("requests").setLevel(log_level_requests)
    logging.info('Zabbix Cachet v.{} started'.format(__version__))
    inc_update_t = threading.Thread()
    event = threading.Event()
    try:
        zapi = Zabbix(
            ZABBIX['server'],
            ZABBIX['user'],
            ZABBIX['pass'],
            ZABBIX['https-verify']
        )

        cachet = Cachet(
            CACHET['server'],
            CACHET['token'],
            CACHET['https-verify']
        )

        zbxtr2cachet = ''

        # Create mapping between metrics and IT services
        metrics_mapping = init_metrics(SETTINGS['metric_services'])

        # Run metric updater
        metric_update_t = threading.Thread(
            name='Metrics Updater',
            target=metrics_updater_worker,
            args=(metrics_mapping, SETTINGS['update_metric_interval'])
        )

        metric_update_t.daemon = True
        metric_update_t.start()

        while True:
            logging.debug('Getting list of Zabbix IT Services ...')
            itservices = (zapi.get_itservices(SETTINGS['root_service']))

            logging.debug('Zabbix IT Services: {}'.format(itservices))
            # Create Cachet components and components groups
            logging.debug('Syncing Zabbix with Cachet...')
            zbxtr2cachet_new = init_cachet(itservices)

            if not zbxtr2cachet_new:
                logging.error('Sorry, can not create Zabbix <> Cachet mapping '
                              'for you. Please check above errors'
                              )
                sys.exit(1)
            else:
                logging.info('Successfully synced Cachet components '
                             'with Zabbix Services'
                             )

            # Restart triggers_watcher_worker
            if zbxtr2cachet != zbxtr2cachet_new:
                zbxtr2cachet = zbxtr2cachet_new
                logging.info('Restart triggers_watcher worker')
                logging.debug('List of watching triggers {}'
                              .format(str(zbxtr2cachet))
                              )
                event.set()
                # Wait until tread die
                while inc_update_t.is_alive():
                    time.sleep(1)
                event.clear()

                inc_update_t = threading.Thread(
                    name='Trigger Watcher',
                    target=triggers_watcher_worker,
                    args=(zbxtr2cachet, SETTINGS['update_inc_interval'], event)
                )

                inc_update_t.daemon = True
                inc_update_t.start()
            time.sleep(SETTINGS['update_comp_interval'])
    except KeyboardInterrupt:
        event.set()
        logging.info('Shutdown requested. See you.')
    except Exception as e:
        logging.error(e)
        exit_status = 1
    sys.exit(exit_status)
