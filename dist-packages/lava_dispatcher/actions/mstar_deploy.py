# -*- coding: utf-8 -*-
#
# Author: Wang Bo <wang.bo@whaley.cn>
# Created time: 2016.01.14, add deploy class to MStar platform


from lava_dispatcher.actions import BaseAction


class cmd_deploy_mstar_image(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'image': {'type': 'string', 'optional': True},
            'image_server_ip': {'type': 'string', 'optional': True},
            'rootfstype': {'type': 'string', 'optional': True},
            'bootloadertype': {'type': 'string', 'optional': True,
                               'default': 'u_boot'},
            'role': {'type': 'string', 'optional': True},
        },
        'additionalProperties': False,
    }

    @classmethod
    def validate_parameters(cls, parameters):
        super(cmd_deploy_mstar_image, cls).validate_parameters(parameters)
        if 'image' not in parameters:
            raise ValueError('must specify image in mstar deploying')
        if 'image_server_ip' not in parameters:
            raise ValueError('must specify server ip address in mstar deploying')

    def run(self, image=None, image_server_ip=None,
            rootfstype='ext4', bootloadertype='u_boot',
            customize=None):
        if customize is not None:
            self.client.config.customize = customize
        self.client.deploy_mstar(image=image, image_server_ip=image_server_ip,
                                 rootfstype=rootfstype, bootloadertype=bootloadertype)
