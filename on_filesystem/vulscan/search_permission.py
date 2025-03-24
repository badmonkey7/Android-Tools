import os
import sys
import subprocess
import json
import tempfile
from xml.dom import minidom

def run_command(cmds, cwd='.'):
    return subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd).communicate()[0]

def parse_android_manifest(apk_file, output_file):
    return run_command(['androguard', 'axml', '-o', output_file, apk_file])

def get_android_name(element):
    return element.getAttribute('android:name')

def get_android_protection_level(element):
    return element.getAttribute('android:protectionLevel')

def get_package_name(manifest):
    return manifest.getAttribute('package')

def get_application(manifest):
    applications = manifest.getElementsByTagName('application')
    if len(applications) > 0:
        return applications[0]
    else:
        return None

def get_defined_permissions(manifest):
    permissions = manifest.getElementsByTagName('permission')
    permissions_name_level = []
    for permission in permissions:
        name = get_android_name(permission)
        protection_level = get_android_protection_level(permission)
        permissions_name_level.append({'name': name, 'protectionLevel': protection_level})
    return permissions_name_level

# https://developer.android.com/reference/android/R.attr#protectionLevel
def is_permission_privileged(defined_permission):
    if defined_permission['protectionLevel'] == '':
        return False
    protectionLevelInt = int(defined_permission['protectionLevel'], base=16)
    if protectionLevelInt | 1000 == 1:
        return False
    if protectionLevelInt | 1 == 1:
        return False
    return True

def get_uses_permissions(manifest):
    uses_permissions = manifest.getElementsByTagName('uses-permission')
    uses_permissions_name = []
    for uses_permission in uses_permissions:
        name = get_android_name(uses_permission)
        uses_permissions_name.append(name)
    return uses_permissions_name

def get_protected_broadcast(manifest):
    protected_broadcasts = manifest.getElementsByTagName('protected-broadcast')
    protected_broadcast_name = []
    for protected_broadcast in protected_broadcasts:
        name = get_android_name(protected_broadcast)
        protected_broadcast_name.append(name)
    return protected_broadcast_name
        
def get_activities(application):
    return application.getElementsByTagName('activity')

def get_services(application):
    return application.getElementsByTagName('service')

def get_content_providers(application):
    return application.getElementsByTagName('provider')

def get_broadcast_receivers(application):
    return application.getElementsByTagName('receiver')

def get_component_intent_filters(component):
    return component.getElementsByTagName('intent-filter')

def get_intent_filter_actions(intent_filter):
    return intent_filter.getElementsByTagName('action')

def get_all_action_names(component):
    intent_filters = get_component_intent_filters(component)
    action_names = []
    for intent_filter in intent_filters:
        actions = get_intent_filter_actions(intent_filter)
        for action in actions:
            action_names.append(get_android_name(action))
    return action_names

def is_component_exported(component):
    exported = component.getAttribute('android:exported')
    if exported == 'true':
        return True
    elif exported =='false':
        return False
    else:
        return len(get_component_intent_filters(component)) != 0

def get_componment_permission(componment):
    return componment.getAttribute('android:permission')

def get_provider_read_permission(provider):
    return provider.getAttribute('android:readPermission')

def get_provider_write_permission(provider):
    return provider.getAttribute('android:writePermission')

def get_provider_path(provider):
    return provider.getAttribute('android:path')

def get_provider_path_prefix(provider):
    return provider.getAttribute('android:pathPrefix')

def get_provider_path_pattern(provider):
    return provider.getAttribute('android:pathPattern')

def get_provider_path_permission(provider):
    return provider.getElementsByTagName('path-permission')

def collect_permission_info(xml_content):
    manifest_file_content = minidom.parse(xml_content)

    manifest = manifest_file_content.documentElement
    package_name = get_package_name(manifest)
    application = get_application(manifest)
    defined_permissions = get_defined_permissions(manifest)
    uses_permissions = get_uses_permissions(manifest)
    protected_broadcasts = get_protected_broadcast(manifest)

    if application == None:
        print('Cannot get application tag in ' + package_name)
        return None

    activities = get_activities(application)
    services = get_services(application)
    providers = get_content_providers(application)
    receivers = get_broadcast_receivers(application)

    componments = []
    
    for activity in activities:
        if is_component_exported(activity):
            full_componment_name = package_name + '/' + get_android_name(activity)
            permission = get_componment_permission(activity)
            componments.append({
                'name': full_componment_name,
                'type': 'activity',
                'permission': permission,
            })
    
    for service in services:
        if is_component_exported(service):
            full_componment_name = package_name + '/' + get_android_name(service)
            permission = get_componment_permission(service)
            componments.append({
                'name': full_componment_name,
                'type': 'service',
                'permission': permission,
            })
    
    for provider in providers:
        if is_component_exported(provider):
            full_componment_name = package_name + '/' + get_android_name(provider)
            permission = get_componment_permission(provider)
            read_permission = get_provider_read_permission(provider)
            write_permission = get_provider_write_permission(provider)
            path_permission = []
            for path_permission_element in get_provider_path_permission(provider):
                path = get_provider_path(path_permission_element)
                path_prefix = get_provider_path_prefix(path_permission_element)
                path_pattern = get_provider_path_pattern(path_permission_element)
                path_permission_def = get_componment_permission(path_permission_element)
                path_read_permission = get_provider_read_permission(path_permission_element)
                path_write_permission = get_provider_write_permission(path_permission_element)
                path_permission.append({
                    'path': path,
                    'pathPrefix': path_prefix,
                    'pathPattern': path_pattern,
                    'permission': path_permission_def,
                    'readPermission': path_read_permission,
                    'writePermission': path_write_permission
                })
                
            componments.append({
                'name': full_componment_name,
                'type': 'provider',
                'permission': permission,
                'readPermission': read_permission,
                'writePermission': write_permission,
                'path_permission': path_permission
            })
    
    for receiver in receivers:
        if is_component_exported(receiver):
            full_componment_name = package_name + '/' + get_android_name(receiver)
            permission = get_componment_permission(receiver)
            action_names = get_all_action_names(receiver)
            componments.append({
                'name': full_componment_name,
                'type': 'receiver',
                'actions': action_names,
                'permission': permission,
            })
    result = {
        'componments': componments,
        'defined_permissions': defined_permissions,
        'uses_permissions': uses_permissions,
        'protected_broadcasts': protected_broadcasts
    }
    return package_name, result

def search_componment_permission_issues(base_data):
    undef_pem_comps = {
        'activity': [],
        'service': [],
        'provider': [],
        'receiver': []
    }
    unpriv_pem_comps = {
        'activity': [],
        'service': [],
        'provider': [],
        'receiver': []
    }
    base_data_merge = {
        'componments': [],
        'defined_permissions': [],
        'uses_permissions': [],
        'protected_broadcasts': []
    }
    for per_apk_data in base_data:
        base_data_merge['componments'].extend(per_apk_data['componments'])
        base_data_merge['defined_permissions'].extend(per_apk_data['defined_permissions'])
        base_data_merge['uses_permissions'].extend(per_apk_data['uses_permissions'])
        base_data_merge['protected_broadcasts'].extend(per_apk_data['protected_broadcasts'])
    
    for componment in base_data_merge['componments']:
        unprivileged = {
            'writePermission': True,
            'readPermission': True,
            'permission': True
        }
        undefined = {
            'writePermission': True,
            'readPermission': True,
            'permission': True
        }
        # Provider has readPermission and writePermission, will use special check logic.
        if componment['type'] == 'provider':
            provider_pem_key_words = ['writePermission', 'readPermission', 'permission']
            for pem_key_word in provider_pem_key_words:
                if pem_key_word in componment and componment[pem_key_word] != '':
                    for defined_permission in base_data_merge['defined_permissions']:
                        if defined_permission['name'] == componment[pem_key_word]:
                            undefined[pem_key_word] = False
                            if is_permission_privileged(defined_permission):
                                unprivileged[pem_key_word] = False
                            break
                else:
                    unprivileged[pem_key_word] = True
                    undefined[pem_key_word] = False

            # Check path permission
            for per_path_permission in componment['path_permission']:
                for pem_key_word in provider_pem_key_words:
                    if pem_key_word in per_path_permission and per_path_permission[pem_key_word] != '':
                        for defined_permission in base_data_merge['defined_permissions']:
                            if defined_permission['name'] == per_path_permission[pem_key_word]:
                                undefined[pem_key_word] = False
                                if is_permission_privileged(defined_permission):
                                    unprivileged[pem_key_word] = False
                                break
                    else:
                        unprivileged[pem_key_word] = True
                        undefined[pem_key_word] = False


            # readPermission or writePermission undefined, and permission unprivileged or undefined.
            # the undefined readPermission/writePermission is vulnerable.
            if (unprivileged['permission'] or undefined['permission']) and (undefined['writePermission'] or undefined['readPermission']):
                undef_pem_comps[componment['type']].append({
                    'name': componment['name'],
                    'writePermission': componment['writePermission'],
                    'readPermission': componment['readPermission'],
                    'permission': componment['permission'],
                    'path_permission': componment['path_permission']
                })
            # permission undefined, and readPermission or writePermission unprivileged.
            # the undefined permission is vulnerable.
            elif undefined['permission'] and (unprivileged['readPermission'] or unprivileged['writePermission']):
                undef_pem_comps[componment['type']].append({
                    'name': componment['name'],
                    'writePermission': componment['writePermission'],
                    'readPermission': componment['readPermission'],
                    'permission': componment['permission'],
                    'path_permission': componment['path_permission']
                })
            # permission unprivileged, and readPermission or writePermission unprivileged.
            # the unprivileged permission is vulnerable.
            elif unprivileged['permission'] and (unprivileged['writePermission'] or unprivileged['readPermission']):
                unpriv_pem_comps[componment['type']].append({
                    'name': componment['name'],
                    'writePermission': componment['writePermission'],
                    'readPermission': componment['readPermission'],
                    'permission': componment['permission'],
                    'path_permission': componment['path_permission']
                })
        # Other componments only have permission, use normal logic.
        else:
            if 'permission' in componment and componment['permission'] != '':
                for defined_permission in base_data_merge['defined_permissions']:
                    if defined_permission['name'] == componment['permission']:
                        undefined['permission'] = False
                        if is_permission_privileged(defined_permission):
                            unprivileged['permission'] = False
                        break
            else:
                unprivileged['permission'] = True
                undefined['permission'] = False
            if componment['type'] == 'receiver':
                # Exported receiver should have an intent filter with unprotected action if is vulnerable. 
                has_unprotected_action = False
                for action in componment['actions']:
                    if action not in base_data_merge['protected_broadcasts']:
                        has_unprotected_action = True
                        break
                if has_unprotected_action == False:
                    continue

            if undefined['permission']:
                undef_pem_comps[componment['type']].append({
                    'name': componment['name'],
                    'permission': componment['permission']
                })
            elif unprivileged['permission']:
                unpriv_pem_comps[componment['type']].append({
                    'name': componment['name'],
                    'permission': componment['permission']
                })
    final_result = {}
    final_result['undefined_permissions'] = undef_pem_comps
    final_result['unprivileged_permissions'] = unpriv_pem_comps
    return final_result

def process_apk(apk_file):
    print('Start analysis apk file: '+apk_file)
    _, output_file = tempfile.mkstemp()
    parse_android_manifest(apk_file, output_file)
    return collect_permission_info(output_file)

def scan_dir(packages_dir):
    base_data = []

    for package in os.listdir(packages_dir):
        if 'auto_generated_rro_product' in package:
            print('Skip auto_generated_rro_product: ' + package)
            continue
        package_dir = packages_dir + os.sep + package
        if os.path.isdir(package_dir):
            for file in os.listdir(package_dir):
                if 'auto_generated_rro_product' in file:
                    print('Skip auto_generated_rro_product apk: ' + file)
                    continue
                if 'auto_generated_rro_product' in file:
                    print('Skip auto_generated_rro_product apk: ' + file)
                    continue
                if file.endswith('.apk'):
                    apk_file = package_dir + os.sep + file
                    if os.path.isfile(apk_file):
                        package_name, tmp_result = process_apk(apk_file)
                        if tmp_result == None:
                            continue
                        base_data.append({
                            'package': package_name,
                            'filename': apk_file,
                            'componments': tmp_result['componments'],
                            'defined_permissions': tmp_result['defined_permissions'],
                            'uses_permissions': tmp_result['uses_permissions'],
                            'protected_broadcasts': tmp_result['protected_broadcasts'],
                        })
                        
        elif package.endswith('.apk'):
            apk_file = package_dir
            if os.path.isfile(apk_file):
                package_name, tmp_result = process_apk(apk_file)
                if tmp_result == None:
                    continue
                base_data.append({
                    'package': package_name,
                    'filename': apk_file,
                    'componments': tmp_result['componments'],
                    'defined_permissions': tmp_result['defined_permissions'],
                    'uses_permissions': tmp_result['uses_permissions'],
                    'protected_broadcasts': tmp_result['protected_broadcasts'],
                })
    return base_data

def main():
    if len(sys.argv) != 2:
        print('search_permission.py: Missing parameters, usage: python search_permission.py dir')
        sys.exit(1)
    
    base_data = {}
    if os.path.exists(sys.argv[1] + os.sep + 'all_comp.json'):
        with open(sys.argv[1] + os.sep + 'all_comp.json', 'r') as f:
            base_data = json.load(f)
    else:
        base_data = scan_dir(sys.argv[1] + os.sep + 'packages')
    
    with open(sys.argv[1] + os.sep + 'all_comp.json', 'w') as f:
        f.write(json.dumps(base_data))
    
    print('Start analysis componment permissions...')
    final_result = search_componment_permission_issues(base_data)
    with open(sys.argv[1] + os.sep + 'accessible_comp.json', 'w') as f:
        f.write(json.dumps(final_result))

    print('Finish!')
    
if __name__ == '__main__':
    main()