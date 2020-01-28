#!/usr/bin/env python3
"""
Polyglot v2 node server for WiFiLogger2
"""
import datetime
import json

import httplib2
import math
import polyinterface
import sys
import syslog

import uom
import write_profile

LOGGER = polyinterface.LOGGER


def convert_to_float(value):
    try:
        return float(value)
    except:
        return 0


def f_to_c(value):
    return (value - 32) * 5.0 / 9.0


class Controller(polyinterface.Controller):
    def __init__(self, polyglot):
        super(Controller, self).__init__(polyglot)
        self.name = 'MeteoHub'
        self.address = 'bb_meteohub'
        self.primary = self.address
        self.ip = ""
        self.units = 'us'
        self.temperature_list = {}
        self.humidity_list = {}
        self.pressure_list = {}
        self.wind_list = {}
        self.rain_list = {}
        self.light_list = {}
        self.lightning_list = {}
        self.myConfig = {}  # custom parameters

        self.poly.onConfig(self.process_config)

    def process_config(self, config):
        if 'customParams' in config:
            if config['customParams'] != self.myConfig:
                # Configuration has changed, we need to handle it
                LOGGER.info('New configuration, updating configuration')
                self.set_configuration(config)
                self.setup_nodedefs(self.units)
                self.discover()
                self.myConfig = config['customParams']

                # Remove all existing notices
                self.removeNoticesAll()

                # Add notices about missing configuration
                if self.ip == "":
                    self.addNotice("IP/Host address of the WiFiLogger2 device is required.")

    def start(self):
        LOGGER.info('Starting WiFiLogger2 Node Server')
        self.check_params()
        self.discover()
        LOGGER.info('WiFiLogger2 Node Server Started.')

    def shortPoll(self):
        pass

    def get_data(self):
        #
        # Get the latest data
        url = "http://" + self.ip + "/wflexp.json"

        #
        # Pull the data
        h = httplib2.Http()
        resp, content = h.request(url, "GET")
        if resp.status != 200:
            syslog.syslog(syslog.LOG_INFO, "Bad response from WiFiLogger2 " + str(resp))
            print(datetime.datetime.now().time(), " -  Bad response from WiFiLogger2. " + str(resp))

        return json.loads(content.decode('utf-8'))

    def longPoll(self):
        # http get and read data
        if self.ip == "":
            print(datetime.datetime.now().time(), " -  No IP/URL for WiFiLogger2.")
            return

        LOGGER.info("LongPoll")

        try:
            #
            # Get the latest data
            wifi_logger_data = self.get_data()

            try:
                # Parse the JSON data

                #
                # Light
                self.nodes['light'].setDriver(uom.LITE_DRVS['uv'], convert_to_float(wifi_logger_data["uv"]))
                self.nodes['light'].setDriver(uom.LITE_DRVS['solar_radiation'],
                                              convert_to_float(wifi_logger_data["solar"]))

                #
                # Rain
                self.nodes['rain'].setDriver(uom.RAIN_DRVS['rate'], convert_to_float(wifi_logger_data["rainr"]))
                self.nodes['rain'].setDriver(uom.RAIN_DRVS['total'], convert_to_float(wifi_logger_data["rain24"]))

                #
                # Temperature
                self.nodes['temperature'].setDriver(uom.TEMP_DRVS['dewpoint'],
                                                    f_to_c(convert_to_float(wifi_logger_data["dew"])))
                self.nodes['temperature'].setDriver(uom.TEMP_DRVS['main'],
                                                    f_to_c(convert_to_float(wifi_logger_data["tempout"])))
                self.nodes['temperature'].setDriver(uom.TEMP_DRVS['windchill'],
                                                    f_to_c(convert_to_float(wifi_logger_data["chill"])))

                #
                # Humidity
                self.nodes['humidity'].setDriver(uom.HUMD_DRVS['main'], convert_to_float(wifi_logger_data["humout"]))

                #
                # Pressure
                self.nodes['pressure'].setDriver(uom.PRES_DRVS['station'], convert_to_float(wifi_logger_data["bartr"]))
                self.nodes['pressure'].setDriver(uom.PRES_DRVS['sealevel'], convert_to_float(wifi_logger_data["bar"]))

                #
                # Wind
                self.nodes['wind'].setDriver(uom.WIND_DRVS['windspeed'], convert_to_float(wifi_logger_data["windspd"]))
                self.nodes['wind'].setDriver(uom.WIND_DRVS['gustspeed'], convert_to_float(wifi_logger_data["gust"]))
                self.nodes['wind'].setDriver(uom.WIND_DRVS['winddir'], convert_to_float(wifi_logger_data["winddir"]))

            except Exception as e:
                LOGGER.error("Failure while parsing WiFiLogger2 data. " + str(e))

        except Exception as e:
            LOGGER.error("Failure trying to connect to WiFiLogger2 device. " + str(e))

    def query(self):

        for node in self.nodes:
            self.nodes[node].reportDrivers()

    def discover(self, *args, **kwargs):
        """
        Add nodes for basic sensor type data
                - Temperature (temp, dewpoint, heat index, wind chill, feels)
                - Humidity
                - Pressure (abs, sealevel, trend)
                - Wind (speed, gust, direction, gust direction, etc.)
                - Precipitation (rate, hourly, daily, weekly, monthly, yearly)
                - Light (UV, solar radiation, lux)
                - Lightning (strikes, distance)

        The nodes need to have their drivers configured based on the user
        supplied configuration. To that end, we should probably create the
        node, update the driver list, set the units and then add the node.
        """
        LOGGER.info("Creating nodes.")
        node = TemperatureNode(self, self.address, 'temperature', 'Temperatures')
        node.SetUnits(self.units);
        for d in self.temperature_list:
            node.drivers.append(
                {
                    'driver': uom.TEMP_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.temperature_list[d]]
                })
        self.addNode(node)

        node = HumidityNode(self, self.address, 'humidity', 'Humidity')
        node.SetUnits(self.units);
        for d in self.humidity_list:
            node.drivers.append(
                {
                    'driver': uom.HUMD_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.humidity_list[d]]
                })
        self.addNode(node)

        node = PressureNode(self, self.address, 'pressure', 'Barometric Pressure')
        node.SetUnits(self.units);
        for d in self.pressure_list:
            node.drivers.append(
                {
                    'driver': uom.PRES_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.pressure_list[d]]
                })
        self.addNode(node)

        node = WindNode(self, self.address, 'wind', 'Wind')
        node.SetUnits(self.units);
        for d in self.wind_list:
            node.drivers.append(
                {
                    'driver': uom.WIND_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.wind_list[d]]
                })
        self.addNode(node)

        node = PrecipitationNode(self, self.address, 'rain', 'Precipitation')
        node.SetUnits(self.units);
        for d in self.rain_list:
            node.drivers.append(
                {
                    'driver': uom.RAIN_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.rain_list[d]]
                })
        self.addNode(node)

        node = LightNode(self, self.address, 'light', 'Illumination')
        node.SetUnits(self.units);
        for d in self.light_list:
            node.drivers.append(
                {
                    'driver': uom.LITE_DRVS[d],
                    'value': 0,
                    'uom': uom.UOM[self.light_list[d]]
                })
        self.addNode(node)

    def delete(self):
        self.stopping = True
        LOGGER.info('Removing WiFiLogger2 node server.')

    def stop(self):
        self.stopping = True
        LOGGER.debug('Stopping WiFiLogger2 node server.')

    def check_params(self):
        self.set_configuration(self.polyConfig)
        self.setup_nodedefs(self.units)

        # Make sure they are in the params  -- does this cause a
        # configuration event?
        LOGGER.info("Adding configuration")
        self.addCustomParam({
            'IPAddress': self.ip,
            'Units': self.units,
        })

        self.myConfig = self.polyConfig['customParams']

        # Remove all existing notices
        LOGGER.info("remove all notices")
        self.removeNoticesAll()

        # Add a notice?
        if self.ip == "":
            self.addNotice("IP/Host address of the WiFiLogger2 device is required.")

    def set_configuration(self, config):
        default_ip = ""
        default_elevation = 0

        LOGGER.info("Check for existing configuration value")

        if 'IPAddress' in config['customParams']:
            self.ip = config['customParams']['IPAddress']
        else:
            self.ip = default_ip

        if 'Units' in config['customParams']:
            self.units = config['customParams']['Units']
        else:
            self.units = 'us'

        return self.units

    def setup_nodedefs(self, units):

        # Configure the units for each node driver
        self.temperature_list['main'] = 'I_TEMP_F'
        self.temperature_list['dewpoint'] = 'I_TEMP_F'
        self.temperature_list['windchill'] = 'I_TEMP_F'
        self.humidity_list['main'] = 'I_HUMIDITY'
        self.pressure_list['station'] = 'I_INHG'
        self.pressure_list['sealevel'] = 'I_INHG'
        self.wind_list['windspeed'] = 'I_MPH'
        self.wind_list['gustspeed'] = 'I_MPH'
        self.wind_list['winddir'] = 'I_DEGREE'
        self.rain_list['rate'] = 'I_INHR'
        self.rain_list['total'] = 'I_INCHES'
        self.light_list['uv'] = 'I_UV'
        self.light_list['solar_radiation'] = 'I_RADIATION'

        # Build the node definition
        LOGGER.info('Creating node definition profile based on config.')
        write_profile.write_profile(LOGGER, self.temperature_list,
                                    self.humidity_list, self.pressure_list,
                                    self.wind_list,
                                    self.rain_list, self.light_list,
                                    self.lightning_list)

        # push updated profile to ISY
        try:
            self.poly.installprofile()
        except:
            LOGGER.error('Failed up push profile to ISY')

    def remove_notices_all(self, command):
        LOGGER.info('remove_notices_all:')
        # Remove all existing notices
        self.removeNoticesAll()

    def update_profile(self, command):
        st = self.poly.installprofile()
        return st

    def SetUnits(self, u):
        self.units = u

    id = 'MeteoHub'
    name = 'udi-poly-meteohub'
    address = 'mbweather'
    stopping = False
    hint = 0xffffff
    units = 'metric'
    commands = {
        'DISCOVER': discover,
        'UPDATE_PROFILE': update_profile,
        'REMOVE_NOTICES_ALL': remove_notices_all
    }
    # Hub status information here: battery and rssi values.
    drivers = [
        {'driver': 'ST', 'value': 1, 'uom': 2},
        {'driver': 'GV0', 'value': 0, 'uom': 72},
    ]


class TemperatureNode(polyinterface.Node):
    id = 'temperature'
    hint = 0xffffff
    units = 'metric'
    drivers = []

    def SetUnits(self, u):
        self.units = u

    def Dewpoint(self, t, h):
        b = (17.625 * t) / (243.04 + t)
        rh = h / 100.0
        c = math.log(rh)
        dewpt = (243.04 * (c + b)) / (17.625 - c - b)
        return round(dewpt, 1)

    def ApparentTemp(self, t, ws, h):
        wv = h / 100.0 * 6.105 * math.exp(17.27 * t / (237.7 + t))
        at = t + (0.33 * wv) - (0.70 * ws) - 4.0
        return round(at, 1)

    def Windchill(self, t, ws):
        # really need temp in F and speed in MPH
        tf = (t * 1.8) + 32
        mph = ws / 0.44704

        wc = 35.74 + (0.6215 * tf) - (35.75 * math.pow(mph, 0.16)) + (
            0.4275 * tf * math.pow(mph, 0.16))

        if (tf <= 50.0) and (mph >= 5.0):
            return round((wc - 32) / 1.8, 1)
        else:
            return t


    def setDriver(self, driver, value):

        super(TemperatureNode, self).setDriver(driver, round(value, 1), report=True,
                                               force=True)


class HumidityNode(polyinterface.Node):
    id = 'humidity'
    hint = 0xffffff
    units = 'metric'
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 22}]

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(HumidityNode, self).setDriver(driver, value, report=True, force=True)


class PressureNode(polyinterface.Node):
    id = 'pressure'
    hint = 0xffffff
    units = 'metric'
    drivers = []
    mytrend = []

    def SetUnits(self, u):
        self.units = u

    # We want to override the SetDriver method so that we can properly
    # convert the units based on the user preference.
    def setDriver(self, driver, value):
        super(PressureNode, self).setDriver(driver, value, report=True, force=True)


class WindNode(polyinterface.Node):
    id = 'wind'
    hint = 0xffffff
    units = 'metric'
    drivers = []

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(WindNode, self).setDriver(driver, value, report=True, force=True)


class PrecipitationNode(polyinterface.Node):
    id = 'precipitation'
    hint = 0xffffff
    units = 'metric'
    drivers = []
    hourly_rain = 0
    daily_rain = 0
    weekly_rain = 0
    monthly_rain = 0
    yearly_rain = 0

    prev_hour = 0
    prev_day = 0
    prev_week = 0

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(PrecipitationNode, self).setDriver(driver, value, report=True,
                                                 force=True)


class LightNode(polyinterface.Node):
    id = 'light'
    units = 'metric'
    hint = 0xffffff
    drivers = []

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(LightNode, self).setDriver(driver, value, report=True, force=True)


class LightningNode(polyinterface.Node):
    id = 'lightning'
    hint = 0xffffff
    units = 'metric'
    drivers = []

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(LightningNode, self).setDriver(driver, value, report=True, force=True)


if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('MeteoHub')
        """
        Instantiates the Interface to Polyglot.
        """
        polyglot.start()
        """
        Starts MQTT and connects to Polyglot.
        """
        control = Controller(polyglot)
        """
        Creates the Controller Node and passes in the Interface
        """
        control.runForever()
        """
        Sits around and does nothing forever, keeping your program running.
        """
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
        """
        Catch SIGTERM or Control-C and exit cleanly.
        """
