# Retexelize operator works only on one linked object!

#globals
image_node_of_og_tex_pms = None
imgae_node_of_copy_pms = None
uvnode_of_og_tex_pms = None
uvnode_of_copy_pms = None
original_connections_pms = {}

bl_info = {
    "name": "PaintMeSurprised",
    "version": (2, 8, 0),
    "blender": (4, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > PaintMeSurprised",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
}

import bpy
import bmesh
import numpy as np
from math import ceil
import mathutils

class PMS_Properties(bpy.types.PropertyGroup):
    #OPTIONS:

    enable_color_picker: bpy.props.BoolProperty(default=False)
    enable_canvas_picker: bpy.props.BoolProperty(default=False)
    enable_camera_picker: bpy.props.BoolProperty(default=False)
    enable_autounwrap: bpy.props.BoolProperty(default=True)
    enable_quickbake: bpy.props.BoolProperty(default=True)

    interpolations : bpy.props.EnumProperty(name="Texture Interpolation", description="Texture interpolation", items=[("Closest", "Closest", ""),("Linear", "Linear", ""), ("Cubic", "Cubic", "")], default="Linear")
    auto_flush_alpha : bpy.props.BoolProperty(default=False)
    lock_alpha : bpy.props.BoolProperty(default=False)
    auto_flush_image: bpy.props.StringProperty(default="")
    force_flush_image: bpy.props.BoolProperty(default=False)
    auto_merge: bpy.props.BoolProperty(default=False)

    #####
    original_canvas: bpy.props.StringProperty(name="ogc", default="", description="")
    camera_name : bpy.props.StringProperty(name='Camera', default="")
    input_image : bpy.props.StringProperty(name="Image", default="", description="Image to use")
    input_uv : bpy.props.StringProperty(name="UV", default="", description="UV to use")
    lock : bpy.props.BoolProperty(name="Lock", default=True)
    safe_to_run : bpy.props.IntProperty(name="safe_to_run", default=0)
    temp_suffix : bpy.props.StringProperty(name="temp_suffix", default="_temp_pms")
    checkpoint_suffix : bpy.props.StringProperty(name="checkpoint_suffix", default="_pms_checkpoint")
    image_mode : bpy.props.EnumProperty(name="Image Algorithm", description="Pixel exchange method between temporary and original images", items=[("none", "Automatic", ""),("mix", "Mixing", ""), ("transfer", "Transfer", "")], default="none")
    paint_both: bpy.props.BoolProperty(name="Paint Both Sides", default=False)
    previous_overlay_state: bpy.props.BoolProperty(default=True)
    previous_paint_state: bpy.props.BoolProperty(default=True)
    uv_adjust : bpy.props.FloatVectorProperty(default=(1.0, 1.0, 1.0))
    mode_before_record : bpy.props.StringProperty(default="EDIT")
    uv_adjust_happened : bpy.props.BoolProperty(default=False)
    uvmap_copy_ref: bpy.props.StringProperty(default="")
    bake_type: bpy.props.EnumProperty(name="Bake Type", description="Bake type", items=[("EMIT", "Emission", "Bake emission only"), ("DIFFUSE", "Diffuse color", "Bake color only"), ("NORMAL", "Normals", "Bake a normal map"), ("COMBINED", "Render", "Bake a combined render according to cycles settings"), ("ALPHA", "Alpha as color", "Special mode that bakes Color using alpha channel as an additional color input")], default="EMIT")
    auto_unwrap: bpy.props.BoolProperty(name="Auto Unwrap", default=False)
    auto_unwrap_algo_smart : bpy.props.BoolProperty(name="Smart Unwrap", default=False)
    isolate_happened: bpy.props.BoolProperty(default=False)
    base_scale: bpy.props.FloatProperty(
        default=1,
        min=0.10,
        max=2,
    )
    input_image_emit: bpy.props.StringProperty(name="Image", default="", description="Image to bake to")
    uv_pixel_count: bpy.props.FloatProperty(default=0)
    show_linked: bpy.props.BoolProperty(name="Show Linked", default=True)
    picker_type : bpy.props.EnumProperty(name="Picker Type", description="Brush/Node Color Picker", items=[("brush", "Brush", ""),("node", "Vector Input", "")], default="brush")
    toggle_order : bpy.props.BoolProperty(default=True)
    node_name: bpy.props.StringProperty(default="")
    input_target: bpy.props.IntProperty(name="Input", default=0, min=0, max=100)
    target_material: bpy.props.PointerProperty(
        name="Target Material",
        description="Material containing the node to control",
        type=bpy.types.Material
    )

def Record(input_image, input_uv, temp_suffix, checkpoint_suffix):
    obj = bpy.context.object

    #emptying globals
    global uvnode_of_og_tex_pms
    global uvnode_of_copy_pms
    uvnode_of_og_tex_pms = None
    uvnode_of_copy_pms = None

    copyTexture(input_image, checkpoint_suffix)

    # Set the image as the active image in the Image Editor
    image_og = bpy.data.images[input_image]
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image_og
            break

    copyUVMAP(input_uv, checkpoint_suffix, input_image)[0]
    uvmap_copy = copyUVMAP(input_uv, temp_suffix, input_image)[0]
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':  # Ensure the object is a mesh
            for uv_map in obj.data.uv_layers:
                if uv_map.name == uvmap_copy.name:
                    obj.data.uv_layers.active = uv_map
                    break  # Exit the loop once the UV map is found
    return uvmap_copy

def get_image_users(image_name):    
    users = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH':  # only consider mesh objects
            for mat in obj.material_slots:
                if mat.material and mat.material.node_tree and any(node.type == 'TEX_IMAGE' and node.image and node.image.name == image_name for node in mat.material.node_tree.nodes):
                    users.append(obj)
    return users

def calculate_uv_scale(image_name1, image_name2):
    def get_image_dimensions(image_name):
        image = bpy.data.images.get(image_name)
        if image:
            return image.size[0], image.size[1]
        else:
            raise ValueError(f"Image '{image_name}' not found")
    
    original_width, original_height = get_image_dimensions(image_name1)
    new_width, new_height = get_image_dimensions(image_name2)
    
    # Calculate the scaling factors for width and height
    width_scale = new_width / original_width
    height_scale = new_height / original_height
    
    # Determine the UV scaling values
    uv_width_scale = 1.0 / width_scale
    uv_height_scale = 1.0 / height_scale
    
    # Format the UV scaling values to two decimal places
    uv_width_scale = round(uv_width_scale, 2)
    uv_height_scale = round(uv_height_scale, 2)
    
    # Check for differences and return appropriate values
    if original_width == new_width and original_height == new_height:
        return 0, 0, 0
    elif original_width == new_width:
        return uv_height_scale, 0, 0
    elif original_height == new_height:
        return uv_width_scale, 0, 0
    else:
        return uv_width_scale, uv_height_scale, 0

def making_image_axtive(target):
    if target in bpy.data.images:
        image = bpy.data.images[target]
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image
            break

def copyTexture(input_image, suffix):
    original_texture = bpy.data.images.get(input_image)
    copy_texture = original_texture.copy()
    copy_texture.name = f"{input_image}{suffix}"
    return copy_texture

def copyUVMAP(input_uv, suffix, input_image):
    processed_meshes = set()
    uvmap_copies = []
    for obj in get_image_users(input_image):
        if obj.data not in processed_meshes:
            processed_meshes.add(obj.data)
            uvmap_copy = obj.data.uv_layers.new()
            uvmap_copy.name = f"{input_uv}{suffix}"
            uvmap_copies.append(uvmap_copy)
    return uvmap_copies
    
def connectNodesForBaking(input_image, temp_suffix, is_bakefullchain):
    # Connections:
    global original_connections_pms
    for obj in bpy.context.selected_objects:
        for material in obj.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree

                original_connections_pms[node_tree] = {}

                image_og_node = None
                if is_bakefullchain == False:
                    for node in node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                            image_og_node = node
                            break
                    print('##############################' + str(image_og_node))
                    for link in image_og_node.inputs["Vector"].links:
                        original_connections_pms[node_tree]['image_vector'] = {
                            'from_socket': link.from_socket,
                            'to_socket': link.to_socket
                        }
                        break

                material_output = None
                for target in ['CYCLES', 'ALL']:  # Priority order
                    for node in node_tree.nodes:
                        if node.type == 'OUTPUT_MATERIAL' and node.target == target:
                            material_output = node
                            break
                    if material_output is not None:
                        break

                if material_output is None:                                              
                    material_output = node_tree.nodes.get("Material Output")

                for link in material_output.inputs["Surface"].links:
                    original_connections_pms[node_tree]['material_output'] = {
                        'from_socket': link.from_socket,
                        'to_socket': link.to_socket
                    }
                    break

                diffnode = node_tree.nodes.get(f"diff{temp_suffix}")
                transnode = node_tree.nodes.get(f"trans{temp_suffix}")
                mixnode = node_tree.nodes.get(f"mix{temp_suffix}")

                # Connect og image nodes to material output
                if image_og_node is not None:
                    node_tree.links.new(image_og_node.outputs["Color"], material_output.inputs["Surface"])

                if diffnode and transnode and mixnode:
                    node_tree.links.new(diffnode.outputs["BSDF"], mixnode.inputs[2])
                    node_tree.links.new(transnode.outputs["BSDF"], mixnode.inputs[1])
                    node_tree.links.new(image_og_node.outputs["Alpha"], mixnode.inputs[0])
                    node_tree.links.new(image_og_node.outputs["Color"], diffnode.inputs["Color"])
                    node_tree.links.new(mixnode.outputs["Shader"], material_output.inputs["Surface"])
                    
                # Connect uv nodes to image nodes
                uv_og_node = node_tree.nodes.get(f"uvog{temp_suffix}")
                image_copy_node = node_tree.nodes.get(f"im{temp_suffix}")
                uv_copy_node = node_tree.nodes.get(f"uvcop{temp_suffix}")

                if uv_og_node and image_og_node:
                    node_tree.links.new(uv_og_node.outputs["UV"], image_og_node.inputs["Vector"])
                if uv_copy_node and image_copy_node:
                    node_tree.links.new(uv_copy_node.outputs["UV"], image_copy_node.inputs["Vector"])

                # Select the copy node
                if image_copy_node is not None:
                    for node in node_tree.nodes:
                        node.select = False
                    image_copy_node.select = True
                    node_tree.nodes.active = image_copy_node
            else:
                pass

    return

def transfer_pixels(source, target, reverse):
    source_image = bpy.data.images.get(source)
    target_image = bpy.data.images.get(target)
    #keep in mind the originals:
    source_name = source_image.name
    target_name = target_image.name

    target_image.name = source_image.name + "_pms_swap"
    source_image.name = target_name
    target_image.name = source_name

    if reverse is False:
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree
                for node in node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name == source_image.name:
                        node.image = target_image
                        break
    else:
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree
                for node in node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name == target_image.name:
                        node.image = source_image
                        break
    making_image_axtive(target)

def transfer_uv(source, target):
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            source_uv = obj.data.uv_layers.get(source)
            target_uv = obj.data.uv_layers.get(target)
            if source_uv and target_uv:
                for loop in obj.data.loops:
                    target_uv.data[loop.index].uv = source_uv.data[loop.index].uv

def rename_uv(input_image, obj):
    matching_objects = get_image_users(str(input_image))
    active_uv_layer = obj.data.uv_layers.active.name
    for obj in matching_objects:
        if obj.type == 'MESH':
            mesh = obj.data
            if not mesh.uv_layers:
                mesh.uv_layers.new(name=active_uv_layer)
            else:
                if mesh.uv_layers.active.name != active_uv_layer:
                    mesh.uv_layers.active.name = active_uv_layer



def restore_connections():
    global original_connections_pms

    for node_tree, connection_data in original_connections_pms.items():
        if connection_data:
            # Restore material output connection
            if 'material_output' in connection_data:
                mat_conn = connection_data['material_output']
                node_tree.links.new(mat_conn['from_socket'], mat_conn['to_socket'])
            
            # Restore image vector connection  
            if 'image_vector' in connection_data:
                img_conn = connection_data['image_vector']
                node_tree.links.new(img_conn['from_socket'], img_conn['to_socket'])   

    original_connections_pms = {}

def cleanup_temp_nodes(temp_suffix, is_bakefullchain):
    global image_node_of_og_tex_pms
    try:
        restore_connections()
    except Exception as e:
        print(f"Error restoring connections: {e}")
    # Remove unneeded nodes from all materials
    for material in bpy.data.materials:
        if material and material.use_nodes:
            nodes = material.node_tree.nodes
            for node in list(nodes):
                if temp_suffix in node.name:
                    nodes.remove(node)

    # Set the original image node as the active selected
    if image_node_of_og_tex_pms is not None and is_bakefullchain == False:
        try:
            image_node_of_og_tex_pms.select = True
            material.node_tree.nodes.active = image_node_of_og_tex_pms
            image_node_of_og_tex_pms = None
        except:
            pass

def cleanup_temp_data(temp_suffix, input_image):
    # Remove unneeded images
    for image in bpy.data.images:
        if temp_suffix in image.name:
            bpy.data.images.remove(image)

    # Remove unneeded UV maps
    matching_objects = get_image_users(input_image)
    for obj in matching_objects:
        for uv_map in obj.data.uv_layers:
        # Check if the UV map name contains '_temp'
            if temp_suffix in uv_map.name:
            # Remove the UV map
                obj.data.uv_layers.remove(uv_map)
        for color_attr in obj.data.color_attributes:
            if temp_suffix in color_attr.name:
                obj.data.color_attributes.remove(color_attr)

def remove_checkpoint_data(checkpoint_suffix, input_image):
    # Remove any existing _pms_checkpoint images
    for image in bpy.data.images:
        if checkpoint_suffix in image.name:
            bpy.data.images.remove(image)

    # Remove any existing _pms_checkpoint UV maps
    matching_objects = get_image_users(input_image)
    for obj in matching_objects:
        for uv_layer in obj.data.uv_layers:
            if checkpoint_suffix in uv_layer.name:
                obj.data.uv_layers.remove(uv_layer)

def Stop(input_image, input_uv, temp_suffix, uvmap_copy_name, is_bakefullchain, bake_type, input_image_emit, alpha, interpolation_override):

    obj = bpy.context.object
    og_obj = obj
    original_interpolations = {}
    # Emptying globals
    global original_connections_pms
    global image_node_of_og_tex_pms
    global imgae_node_of_copy_pms
    original_connections_pms = {}
    image_node_of_og_tex_pms = None
    imgae_node_of_copy_pms = None

    if is_bakefullchain == False or alpha == True:
        matching_objects = get_image_users(input_image)
        og_hidden = []

    def unhide_it():
        bpy.ops.object.select_all(action='DESELECT')
        for member in matching_objects:
            if member.hide_get() is True:
                member.hide_set(False)
                og_hidden.append(member)
            member.select_set(True)
        return og_hidden

    def hide_it(og_hidden):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in og_hidden:
            try:
                obj.hide_set(True)
            except:                
                pass
        og_obj.select_set(True)
        bpy.context.view_layer.objects.active = og_obj
    
    if is_bakefullchain == False:
        copy_texture = copyTexture(input_image, temp_suffix)
        unhide_it()

       # Get node tree ref from all materials
        processed_materials = set()
        for objectum in matching_objects:
            for material in objectum.data.materials:
                if material in processed_materials:
                    continue  # Skip if we already processed this material
                processed_materials.add(material)

                if material.use_nodes:
                    node_tree = material.node_tree

                    imgae_node_of_copy_pms = node_tree.nodes.new(type="ShaderNodeTexImage")
                    imgae_node_of_copy_pms.name = f"im{temp_suffix}"
                    imgae_node_of_copy_pms.image = bpy.data.images.get(copy_texture.name)

                    # Find og image node and store reference
                    for node in node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                            image_node_of_og_tex_pms = node
                            # Make new uvmap nodes for each and store reference
                            uvnode_of_og_tex_pms = node_tree.nodes.new(type='ShaderNodeUVMap')
                            uvnode_of_og_tex_pms.name = f"uvog{temp_suffix}"
                            uvnode_of_og_tex_pms.uv_map = input_uv
                            uvnode_of_copy_pms = node_tree.nodes.new(type='ShaderNodeUVMap')
                            uvnode_of_copy_pms.name = f"uvcop{temp_suffix}"
                            uvnode_of_copy_pms.uv_map = uvmap_copy_name
                            if bake_type == 'DIFFUSE': 
                                transparent_node = node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
                                transparent_node.name = f"trans{temp_suffix}"
                                mix_shader_node = node_tree.nodes.new(type='ShaderNodeMixShader')
                                mix_shader_node.name = f"mix{temp_suffix}"
                                diffuse_node = node_tree.nodes.new(type='ShaderNodeBsdfDiffuse')
                                diffuse_node.name = f"diff{temp_suffix}"
                            break
    else:
        if alpha == True:
            unhide_it()

        for objectum in bpy.context.selected_objects:
            for material in objectum.data.materials:
                if material.use_nodes:
                    node_tree = material.node_tree

                    input_image_for_emit = bpy.data.images.get(input_image_emit)                
                    if input_image_for_emit is None:                   
                        new_image = bpy.data.images.new('pms_baked', 1024, 1024)   

                        if input_image_emit != "":
                            new_image.name = input_image_emit

                    input_image_emit_node = node_tree.nodes.new(type="ShaderNodeTexImage")
                    input_image_emit_node.name = f"im{temp_suffix}"
                    input_image_emit_node.image = bpy.data.images.get(input_image_emit)
                    
                    node_tree.nodes.active = None
                    node_tree.nodes.active = input_image_emit_node

                    # Make new uvmap nodes for each and store reference
                    uvnode_of_og_tex_pms = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_og_tex_pms.name = f"uvog{temp_suffix}"
                    uvnode_of_og_tex_pms.uv_map = input_uv
                    uvnode_of_copy_pms = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_copy_pms.name = f"uvcop{temp_suffix}"
                    uvnode_of_copy_pms.uv_map = input_uv
        
    connectNodesForBaking(input_image, temp_suffix, is_bakefullchain)

    try:
        # Change the interpolation to 'Closest'
        for node in node_tree.nodes:
            if is_bakefullchain == False:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                    original_interpolations[node] = node.interpolation
            else:
                if node.type == 'TEX_IMAGE':
                    original_interpolations[node] = node.interpolation
        for node, original_interpolation in original_interpolations.items():
            node.interpolation = interpolation_override

        # Store the current render settings and switch to Cycles for baking
        original_render_engine = bpy.context.scene.render.engine
        original_margin_type = bpy.context.scene.render.bake.margin_type
        original_margine_size = bpy.context.scene.render.bake.margin
        original_samples = bpy.context.scene.cycles.samples
        original_bounces = bpy.context.scene.cycles.max_bounces
        original_t_bounces = bpy.context.scene.cycles.transparent_max_bounces
        original_denoise = bpy.context.scene.cycles.use_denoising
        original_filter = bpy.context.scene.render.film_transparent
        original_dir = bpy.context.scene.render.bake.use_pass_direct
        original_indir = bpy.context.scene.render.bake.use_pass_indirect
        original_col = bpy.context.scene.render.bake.use_pass_color

        bpy.context.scene.render.engine = 'CYCLES'

        if bake_type != 'COMBINED':
            bpy.context.scene.cycles.use_denoising = False
            bpy.context.scene.cycles.samples = 1
            bpy.context.scene.cycles.max_bounces = 0
            bpy.context.scene.cycles.transparent_max_bounces = 0
            bpy.context.scene.render.film_transparent = True
            bpy.context.scene.render.bake.use_pass_direct = False
            bpy.context.scene.render.bake.use_pass_indirect = False
            bpy.context.scene.render.bake.use_pass_color = True
           
        bpy.context.scene.render.bake.margin_type = 'EXTEND'
        bpy.context.scene.render.bake.margin = 2
        # Perform the bake operation
        bpy.ops.object.bake(type=bake_type)

    except Exception as e:
        print(f"Error baking: {e}")
    finally:
        # Restore the original interpolation and render engine
        for node, original_interpolation in original_interpolations.items():
            node.interpolation = original_interpolation

        bpy.context.scene.render.engine = original_render_engine
        bpy.context.scene.render.bake.margin_type = original_margin_type
        bpy.context.scene.render.bake.margin = original_margine_size
        bpy.context.scene.cycles.samples = original_samples
        bpy.context.scene.cycles.max_bounces = original_bounces
        bpy.context.scene.cycles.transparent_max_bounces = original_t_bounces
        bpy.context.scene.cycles.use_denoising = original_denoise
        bpy.context.scene.render.film_transparent = original_filter
        bpy.context.scene.render.bake.use_pass_direct = original_dir
        bpy.context.scene.render.bake.use_pass_indirect = original_indir
        bpy.context.scene.render.bake.use_pass_color = original_col        

    # Get the image data from the selected node
    if is_bakefullchain == False:
        try:
            transfer_pixels(input_image + temp_suffix, input_image, True)  
            if uvnode_of_copy_pms is not None:
                transfer_uv(uvnode_of_copy_pms.uv_map, input_uv)
            else:
                print("UV Node of Copy missing!")
        except:
            print("ERROR: DIDNT FIND ANYTHING")

        # Set the UV map as the active UV map
        for obj in matching_objects:
            now_active = obj.data.uv_layers.get(input_uv)
            obj.data.uv_layers.active = now_active
        hide_it(og_hidden)

    elif is_bakefullchain == True and alpha == True:
        hide_it(og_hidden)

    uvnode_of_copy_pms = None
    uvnode_of_og_tex_pms = None
    imgae_node_of_copy_pms = None

class CleanupOperator(bpy.types.Operator):
    bl_idname = "wm.cleanup_operator"
    bl_label = "Cancel"
    bl_description = "Drop the lenses"
    bl_options = {'UNDO'}

    def execute(self, context):
        obj = bpy.context.object
        pms_props = context.scene.pms_properties
        image = bpy.data.images.get(pms_props.input_image)
        if image:
            image.reload()
        cleanup_temp_nodes(pms_props.temp_suffix, False)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
        for uv in bpy.context.object.data.uv_layers:
            if uv.name == pms_props.input_uv:
                bpy.context.object.data.uv_layers.active = uv 
        pms_props.safe_to_run = 0
        pms_props.lock = True
        pms_props.uv_adjust_happened = False
        return {'FINISHED'}

class RecoverOperator(bpy.types.Operator):
    bl_idname = "wm.recover_operator"
    bl_label = "Recover"
    bl_description = "Recover the previous state of uv and texture"
    bl_options = {'UNDO'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        pms_props.safe_to_run += 1
        cleanup_temp_nodes(pms_props.temp_suffix, False)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image, True)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
        pms_props.safe_to_run = 0
        pms_props.lock = True
        return {'FINISHED'}

class Focus_on_Image(bpy.types.Operator):
    bl_idname = "wm.focus_on_image"
    bl_label = "Select Image"
    bl_description = "Select Image in the UV/Image Editor"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        if pms_props.input_image in bpy.data.images:
            image = bpy.data.images[pms_props.input_image]
        else:
            self.report({'ERROR'}, "Input image does not exist!")
            return {'CANCELLED'}
    
    # Set the image as the active image in the Image Editor
        for area in bpy.context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = image
                break
        return {'FINISHED'}

class Select_all_image_users(bpy.types.Operator):
    bl_idname = "wm.focus_on_iu"
    bl_label = "Edit Linked"
    bl_description = "Edit all objects using the input image"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        image_users = get_image_users(pms_props.input_image)
        active = bpy.context.active_object
        mode_before = bpy.context.object.mode
        if active in image_users:

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            for obj in image_users:
                #obj.hide_set(False)
                obj.select_set(True)
            
            bpy.ops.object.mode_set(mode=mode_before)
        else:
            self.report({'ERROR'}, "Select a linked object")
        return {'FINISHED'}

class BakeEmitChain(bpy.types.Operator):
    bl_idname = "wm.bake_emit_chain"
    bl_label = "Bake Emission Chain"
    bl_description = "Bakes shader to an input image."
    #bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        can_run = False
        mode_before = bpy.context.object.mode

        #catching errors:
        if pms_props.bake_type != "ALPHA":
            if pms_props.input_image_emit == "":
                self.report({'ERROR'}, "Input an image name to use or to create!")
                return {'CANCELLED'}
            if pms_props.input_image_emit == pms_props.input_image:
                self.report({'ERROR'}, "Input image is PROTECTED!")
                return {'CANCELLED'}
            
        if pms_props.bake_type == "ALPHA":
            if pms_props.input_image not in bpy.data.images:
                self.report({'ERROR'}, "Input image does not exist!")
                return {'CANCELLED'}
            if bpy.data.images[pms_props.input_image].alpha_mode != 'CHANNEL_PACKED':
                self.report({'ERROR'}, "Input image is not Channel Packed for Alpha!")
                return {'CANCELLED'}

        if pms_props.bake_type == "EMIT" or pms_props.bake_type == "ALPHA":
            obj = bpy.context.object
            materials = obj.data.materials
            for mat in materials:
                node_tree = mat.node_tree
                output_node = node_tree.nodes.get("Material Output")
                if output_node:
                    links = node_tree.links
                    for link in links:
                        if link.to_node == output_node:
                            # Get the node connected to the Material Output node
                            connected_node = link.from_node
                            if 'BSDF' in connected_node.type:
                                self.report({'ERROR'}, f"Material '{mat.name}' has a BSDF shader connected to the output! Surface is required to be shadeless for 'Color' bake type!")
                                return {'CANCELLED'}
  
        bpy.ops.paint.texture_paint_toggle()
        
        if bpy.context.selected_objects:
                can_run = True
        if not can_run: 
            self.report({'ERROR'}, "Select an object!")
            return {'CANCELLED'}
        
        if pms_props.auto_unwrap == True and pms_props.bake_type != "ALPHA":
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.mark_seam(clear=False)
            bpy.ops.uv.smart_project(island_margin=0.0005, scale_to_bounds=False)
            bpy.ops.mesh.mark_seam(clear=True)

        bpy.ops.object.mode_set(mode=mode_before)
        cleanup_temp_data("_bakedfullchain", pms_props.input_image)
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            if pms_props.bake_type != "ALPHA":
                Stop(pms_props.input_image, pms_props.input_uv, "_bakedfullchain", pms_props.uvmap_copy_ref, True, pms_props.bake_type, pms_props.input_image_emit, alpha=False, interpolation_override=pms_props.interpolations)
            else:
                try:
                    bpy.ops.image.save_all_modified()
                except:
                    pass
                img_copy = copyTexture(pms_props.input_image, "_useful_alpha")
                Stop(pms_props.input_image, pms_props.input_uv, "_bakedfullchain", pms_props.uvmap_copy_ref, True, "EMIT", img_copy.name, alpha=True, interpolation_override=pms_props.interpolations)
                og_im = bpy.data.images[pms_props.input_image]
                og_im.pixels = img_copy.pixels[:]
                bpy.data.images.remove(img_copy)
                bpy.ops.wm.focus_on_image()
                bpy.ops.object.mode_set(mode=mode_before)
                try:
                    bpy.ops.image.save_all_modified()
                except:
                    pass
        except:
            self.report({'ERROR'}, "No material is found on this object!")            
            return {'CANCELLED'}
        cleanup_temp_nodes(pms_props.temp_suffix, True)
        cleanup_temp_nodes("_bakedfullchain", True)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        if pms_props.auto_flush_alpha:
            bpy.ops.wm.pms_flush_alpha()
        self.report({'INFO'}, "Bake complete!") 
        return {'FINISHED'}



class BakeSelfEmit(bpy.types.Operator):
    bl_idname = "wm.bake_self_emit"
    bl_label = "Bake Emission Chain To Self"
    bl_description = "Bakes color into the input image."
    #bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        can_run = False
        mode_before = bpy.context.object.mode
            

        if pms_props.input_image not in bpy.data.images:
            self.report({'ERROR'}, "Input image does not exist!")
            return {'CANCELLED'}
        if bpy.data.images[pms_props.input_image].alpha_mode != 'CHANNEL_PACKED':
            self.report({'ERROR'}, "Input image is not Channel Packed for Alpha!")
            return {'CANCELLED'}
  
        bpy.ops.paint.texture_paint_toggle()
        
        if bpy.context.selected_objects:
                can_run = True
        if not can_run: 
            self.report({'ERROR'}, "Select an object!")
            return {'CANCELLED'}
        
        bpy.ops.object.mode_set(mode=mode_before)
        cleanup_temp_data("_bakedfullchain", pms_props.input_image)
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            try:
                bpy.ops.image.save_all_modified()
            except:
                pass
            img_copy = copyTexture(pms_props.input_image, "_useful_alpha")
            Stop(pms_props.input_image, pms_props.input_uv, "_bakedfullchain", pms_props.uvmap_copy_ref, True, "DIFFUSE", img_copy.name, alpha=True, interpolation_override=pms_props.interpolations)
            og_im = bpy.data.images[pms_props.input_image]
            og_im.pixels = img_copy.pixels[:]
            bpy.data.images.remove(img_copy)
            bpy.ops.wm.focus_on_image()
            bpy.ops.object.mode_set(mode=mode_before)
            try:
                bpy.ops.image.save_all_modified()
            except:
                pass
        except:
            self.report({'ERROR'}, "No material is found on this object!")            
            return {'CANCELLED'}
        cleanup_temp_nodes(pms_props.temp_suffix, True)
        cleanup_temp_nodes("_bakedfullchain", True)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        if pms_props.auto_flush_alpha:
            bpy.ops.wm.pms_flush_alpha()
        self.report({'INFO'}, "Bake complete!") 
        return {'FINISHED'}

class UV_reqest_cancel(bpy.types.Operator):
    bl_idname = "wm.request_pms_cancel"
    bl_label = "Cancel"
    bl_description = "Revert UV"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        bpy.ops.object.mode_set(mode='OBJECT')
        transfer_uv(pms_props.input_uv + pms_props.checkpoint_suffix, pms_props.input_uv + pms_props.temp_suffix)
        bpy.ops.object.mode_set(mode='EDIT')
        pms_props.uv_adjust_happened = False
        return {'FINISHED'}

class UV_request(bpy.types.Operator):
    bl_idname = "wm.request_pms"
    bl_label = "Match UV"
    bl_description = "Calculate the difference in UV size from the last checkpoint. Only useful after Resize while editing"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        if pms_props.input_image + pms_props.checkpoint_suffix in bpy.data.images:
            pms_props.uv_adjust = calculate_uv_scale(pms_props.input_image, pms_props.input_image + pms_props.checkpoint_suffix)
            bpy.ops.object.mode_set(mode='OBJECT')
            transfer_uv(pms_props.input_uv + pms_props.checkpoint_suffix, pms_props.input_uv + pms_props.temp_suffix)
            bpy.ops.object.mode_set(mode='EDIT')
        uv_scale_x, uv_scale_y, _ = pms_props.uv_adjust[:]
        if uv_scale_x != 0.0 or uv_scale_y != 0.0:
            bpy.ops.object.mode_set(mode='OBJECT')
            for obj in bpy.context.selected_objects:
                uv_layer = obj.data.uv_layers.get(pms_props.input_uv + pms_props.temp_suffix)
                if uv_layer:
                    for loop in obj.data.loops:
                        uv = uv_layer.data[loop.index].uv
                        if uv_scale_x != 0.0:
                            uv.x = (uv.x - 0.5) / uv_scale_x + 0.5
                        if uv_scale_y != 0.0:
                            uv.y = (uv.y - 0.5) / uv_scale_y + 0.5
            bpy.ops.object.mode_set(mode='EDIT')
            pms_props.uv_adjust_happened = True
        return {'FINISHED'}

class PaintBothSides(bpy.types.Operator):
    bl_idname = "wm.paint_both_sides"
    bl_label = "Paint Both Sides"
    bl_description = "Paint both sides"
    bl_options = {'UNDO'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        if pms_props.paint_both == False:
            settings = context.tool_settings.image_paint
            settings.use_occlude = False
            settings.use_backface_culling = False
            pms_props.paint_both = True
        elif pms_props.paint_both == True:
            settings = context.tool_settings.image_paint
            settings.use_occlude = True
            settings.use_backface_culling = True
            pms_props.paint_both = False
        return {'FINISHED'}

class BRUSH_OT_invert_color_keep_value(bpy.types.Operator):
    """Flip brush hue while keeping the value/brightness"""
    bl_idname = "brush.invert_color_keep_value"
    bl_label = "Flip Brush Hue"
    bl_options = {'REGISTER', 'UNDO'}
       
    def execute(self, context):
        tool_settings = context.scene.tool_settings
        unified_settings = tool_settings.image_paint.unified_paint_settings
        
        # Get the active brush based on current mode
        if unified_settings.use_unified_color:
            brush = context.tool_settings.image_paint.unified_paint_settings
        else:
            brush = context.tool_settings.image_paint.brush
                        
        # Get current brush color
        if hasattr(brush, 'color'):
            current_color = brush.color
            
            # Convert to HSV
            hsv_color = mathutils.Color((current_color.r, current_color.g, current_color.b)).hsv
            h, s, v = hsv_color            
            inverted_h = (h + 0.5) % 1.0  # Opposite on color wheel
            
            # Convert back to RGB with original saturation and value
            inverted_rgb = mathutils.Color()
            inverted_rgb.hsv = (inverted_h, s, v)
            
            # Set new color
            brush.color = (inverted_rgb.r, inverted_rgb.g, inverted_rgb.b)          
        else:
            self.report({'WARNING'}, "Brush doesn't have color property")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class MESH_OT_split_selected_faces(bpy.types.Operator):
    bl_idname = "mesh.split_selected_faces"
    bl_label = "Isolate selected faces to paint"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH')
    
    def execute(self, context):
        split_object_name = "PMS_Dummy_Copy"
        obj = context.active_object
        previous_mode = bpy.context.object.mode        
        split_obj = bpy.data.objects.get(split_object_name)
        
        if split_obj:
            # Remove existing split object
            bpy.data.objects.remove(split_obj, do_unlink=True)
            
            # Unhide all faces on original object
            bpy.ops.object.mode_set(mode='OBJECT')
            
            mesh = obj.data
            for poly in mesh.polygons:
                poly.hide = False
            
            bpy.ops.object.mode_set(mode=previous_mode)
            pms_props = context.scene.pms_properties
            pms_props.isolate_happened = False
            return {'FINISHED'}
        
        # Get selected faces before switching modes
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data
        selected_faces = [poly.index for poly in mesh.polygons if poly.select]
        
        if not selected_faces:
            self.report({'WARNING'}, "No faces selected")
            bpy.ops.object.mode_set(mode='EDIT')
            return {'CANCELLED'}
        
        # Duplicate object
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.duplicate()
        
        split_obj = context.active_object
        split_obj.name = split_object_name
        
        bpy.ops.object.mode_set(mode='EDIT')
        for poly in obj.data.polygons:
            poly.select = poly.index in selected_faces
            poly.hide = not poly.select
        
        for poly in split_obj.data.polygons:
            poly.select = poly.index in selected_faces
            bpy.ops.mesh.delete(type='FACE')

        bpy.ops.object.mode_set(mode='OBJECT')
        # Make original active
        context.view_layer.objects.active = obj
        obj.select_set(True)
        split_obj.select_set(False)
        
        # Back to edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Restore selection
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for poly in obj.data.polygons:
            poly.select = poly.index in selected_faces
        bpy.ops.object.mode_set(mode='EDIT')
        
        pms_props = context.scene.pms_properties
        pms_props.isolate_happened = True
        bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        return {'FINISHED'}

class FlushAlpha(bpy.types.Operator):
    bl_idname = "wm.pms_flush_alpha"
    bl_label = "Clean Up Alpha"
    bl_description = "Set Alpha to 1 on all pixels"

    def execute(self, context):
        mode_before = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        pms_props = context.scene.pms_properties
        flush_images = []
        if pms_props.auto_flush_alpha == True or pms_props.lock_alpha == False:
            image = bpy.data.images.get(pms_props.input_image)
            if image and image.pixels:
                flush_images.append(image)
        if pms_props.auto_flush_image != "" and pms_props.force_flush_image == True:        
            flush_cloak = bpy.data.images.get(pms_props.auto_flush_image)
            if flush_cloak and flush_cloak.pixels:
                flush_images.append(flush_cloak)
            obj_mesh = bpy.context.object.data
            col = obj_mesh.color_attributes.get(pms_props.auto_flush_image)
            if col:
                flush_images.append(col)

        for img in flush_images:
            try:
                if img.pixels:
                    # Pre-allocate array with correct size
                    pixel_count = len(img.pixels)
                    pixels = np.empty(pixel_count, dtype=np.float32)
                    
                    # Use foreach_get to fill the array directly (fast)
                    img.pixels.foreach_get(pixels)
                    try:
                        if img.name == flush_cloak.name:
                            pixels[0::4] = 0.0
                            pixels[1::4] = 0.0
                            pixels[2::4] = 0.0
                    except:
                        pass
                    # Set alpha channels
                    pixels[3::4] = 1.0
                    
                    # Use foreach_set to write back directly (fast)
                    img.pixels.foreach_set(pixels)
                    img.update()
            except:
                for data in col.data:
                    data.color = (0, 0, 0, 1)
                                    
        bpy.ops.object.mode_set(mode=mode_before)
        return {'FINISHED'}

class ForceFlushCloak(bpy.types.Operator):
    bl_idname = "wm.pms_flush_image"
    bl_label = "Clear"
    bl_description = "Set pixels to 0"

    def execute(self, context):
        pms_props = context.scene.pms_properties
        if pms_props.auto_merge:
            bpy.ops.wm.bake_self_emit()
        pms_props.force_flush_image = True
        pms_props.lock_alpha = True
        bpy.ops.wm.pms_flush_alpha()
        pms_props.lock_alpha = False
        pms_props.force_flush_image = False
        return {'FINISHED'}

class SetLinked(bpy.types.Operator):
    bl_idname = "wm.pms_set_linked"
    bl_label = "Show Linked"
    bl_description = "Show linked objects"

    def execute(self, context):
        pms_props = context.scene.pms_properties
        if pms_props.show_linked:
            pms_props.show_linked = False
        else:
            pms_props.show_linked = True
        return {'FINISHED'}

class Show_settings_PMS(bpy.types.Operator):
    bl_idname = "wm.pms_show_settings"
    bl_label = "Settings"
    bl_description = "Shows settings that can be tweaked"

    # Define temporary properties for the dialog
    
    temp_interpolations: bpy.props.EnumProperty(
        name="Texture Interpolation",
        items=[
            ('Closest', "Closest", "No interpolation"),
            ('Linear', "Linear", "Linear interpolation"),
            ('Cubic', "Cubic", "Cubic interpolation")
        ],
        default='Linear'
    )
    
    temp_auto_flush_alpha: bpy.props.BoolProperty(
        name="Auto Flush Alpha",
        default=False
    )

    temp_enable_canvas_picker: bpy.props.BoolProperty(
        name="Enable Canvas Picker Panel",
        default=False
    )

    temp_enable_color_picker: bpy.props.BoolProperty(
        name="Enable Color Picker Panel",
        default=False
    )

    temp_enable_camera_picker: bpy.props.BoolProperty(
        name="Enable Camera Picker Panel",
        default=False
    )

    temp_enable_autounwrap: bpy.props.BoolProperty(
        name="Enable Auto Unwrap Extension",
        default=False
    )

    temp_enable_quickbake: bpy.props.BoolProperty(
        name="Enable Quickbake Extension",
        default=False
    )
    def invoke(self, context, event):
        # Copy current values to temporary properties
        pms_props = context.scene.pms_properties
        self.temp_interpolations = pms_props.interpolations
        self.temp_auto_flush_alpha = pms_props.auto_flush_alpha
        self.temp_enable_canvas_picker = pms_props.enable_canvas_picker
        self.temp_enable_color_picker = pms_props.enable_color_picker
        self.temp_enable_autounwrap = pms_props.enable_autounwrap
        self.temp_enable_quickbake = pms_props.enable_quickbake
        self.temp_enable_camera_picker = pms_props.enable_camera_picker
        
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        version_str = "{}.{}.{}".format(bl_info["version"][0], bl_info["version"][1], bl_info["version"][2])
        layout = self.layout
        layout.label(text="PaintMeSurprised v"+version_str)
        
        box = layout.box()
       
        row = box.row()
        row.label(text="Texture Interpolation")
        row.prop(self, "temp_interpolations", text="")
        row = box.row()
        row.label(text="Auto Flush Alpha")
        row.prop(self, "temp_auto_flush_alpha", text="")

        row = box.row()
        row.label(text="Show Auto Unwrap Extension")
        row.prop(self, "temp_enable_autounwrap", text="") 

        row = box.row()
        row.label(text="Show Quick Baker Extension")
        row.prop(self, "temp_enable_quickbake", text="")  

        row = box.row()
        row.label(text="Show Color Picker Panel")
        row.prop(self, "temp_enable_color_picker", text="")        

        row = box.row()
        row.label(text="Show Canvas Picker Panel")
        row.prop(self, "temp_enable_canvas_picker", text="")

        row = box.row()
        row.label(text="Show Camera Picker Panel")
        row.prop(self, "temp_enable_camera_picker", text="")        

    def execute(self, context):
        # Apply temporary properties to real properties when OK is pressed
        pms_props = context.scene.pms_properties
        pms_props.interpolations = self.temp_interpolations
        pms_props.auto_flush_alpha = self.temp_auto_flush_alpha

        pms_props.enable_canvas_picker = self.temp_enable_canvas_picker
        pms_props.enable_color_picker = self.temp_enable_color_picker 
        pms_props.enable_autounwrap = self.temp_enable_autounwrap
        pms_props.enable_quickbake = self.temp_enable_quickbake
        pms_props.enable_camera_picker = self.temp_enable_camera_picker

        return {'FINISHED'}

    def cancel(self, context):
        pass

class ReloadOperator(bpy.types.Operator):
    bl_idname = "wm.reload_operator"
    bl_label = "Load checkpoint"
    bl_description = "Load the previous state of uv and texture"
    bl_options = {'UNDO'}

    def invoke(self, context, event):
        # Show custom popup menu
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Are you sure you want to load the current checkpoint?")
        layout.label(text="This will restore previous UV and texture state.")

    def execute(self, context):
        pms_props = context.scene.pms_properties
        pms_props.safe_to_run += 1
        obj = bpy.context.object
        cleanup_temp_nodes(pms_props.temp_suffix, False)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image, True)
        for uv_map in obj.data.uv_layers:
            if pms_props.checkpoint_suffix in uv_map.name:
                bpy.ops.object.mode_set(mode='OBJECT')
                transfer_uv(pms_props.input_uv + pms_props.checkpoint_suffix, pms_props.input_uv)
                bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
        pms_props.safe_to_run = 0

        return {'FINISHED'}

class RetexelOperator(bpy.types.Operator):
    bl_idname = "wm.retexel_operator"
    bl_label = "Retexel"
    bl_description = "Regenerate paintable surfaces"
    bl_options = {'UNDO'}

    def execute(self, context):
        bpy.ops.wm.rec_operator()
        bpy.ops.wm.stop_operator()
        return {'FINISHED'}

class UVLayoutManagerWithPixelCheck(bpy.types.Operator):
    bl_idname = "uv.layout_manager_pixel_check"
    bl_label = "Store & Restore UV Layout with Pixel Coverage"
    bl_description = "Unwraps selected while maintaining pixel coverage"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        pms_props = context.scene.pms_properties
        
        try:
            # Step 1: Get original pixel count before unwrap
            original_error, original_pixel_count = self.auto_count_uv_pixels(pms_props.input_image)
            if original_error:
                self.report({'ERROR'}, f"Pre-unwrap: {original_error}")
                return {'CANCELLED'}
                        
            # Step 2: Store original UV bbox and scale
            error_msg, original_bbox = self.store_uv_bbox()
            if error_msg:
                self.report({'ERROR'}, error_msg)
                return {'CANCELLED'}
            
            even_bbox = self.adjust_bbox_to_even(original_bbox)
            original_scale_ratio = self.calculate_scale_ratio(even_bbox)
            
            # Step 3: Perform unwrap
            bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', margin=0.001)
            
            # Step 4: Restore scale and position
            error_msg = self.restore_uv_layout(even_bbox, original_scale_ratio)
            if error_msg:
                self.report({'ERROR'}, error_msg)
                return {'CANCELLED'}
            
            # Step 5: Check new pixel coverage and scale up if needed
            new_error, new_pixel_count = self.auto_count_uv_pixels(pms_props.input_image)
            if new_error:
                self.report({'ERROR'}, f"Post-unwrap: {new_error}")
                return {'CANCELLED'}
                        
            # Step 6: Scale up if new coverage is less than original
            if new_pixel_count != original_pixel_count:
                scale_factor = self.calculate_required_scale(original_pixel_count, new_pixel_count)
                self.scale_uvs_around_center(scale_factor)              
            else:
                pass
        except:
            self.report({'ERROR'}, "Out of Bounds!")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def calculate_required_scale(self, target_pixels, current_pixels):
        """Calculate scale factor needed to achieve target pixel coverage"""
        if current_pixels <= 0:
            return 1.0

        scale_factor = (target_pixels / current_pixels) ** 0.5
        return max(0.1, min(scale_factor, 10.0))
    
    def scale_uvs_around_center(self, scale_factor):
        """Scale selected UVs around their center"""
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return "No mesh selected"
        
        mesh = obj.data
        if not mesh.uv_layers:
            return "No UVs found"
        
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        selected_faces = [f for f in bm.faces if f.select]
        
        if not selected_faces:
            return "No faces selected"
        
        # Calculate center of selected UVs
        all_uvs = [loop[uv_layer].uv for face in selected_faces for loop in face.loops]
        u_coords = [uv.x for uv in all_uvs]
        v_coords = [uv.y for uv in all_uvs]
        
        center_u = (min(u_coords) + max(u_coords)) / 2
        center_v = (min(v_coords) + max(v_coords)) / 2
        
        # Scale around center
        for face in selected_faces:
            for loop in face.loops:
                uv = loop[uv_layer]
                uv.uv.x = center_u + (uv.uv.x - center_u) * scale_factor
                uv.uv.y = center_v + (uv.uv.y - center_v) * scale_factor
        
        bmesh.update_edit_mesh(mesh)
        return None
        
    def auto_count_uv_pixels(self, input_image):
        """Automatically counts pixels with optimized settings"""
        # Get active objects and validate
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return "No mesh selected", 0
        
        mesh = obj.data
        if not mesh.uv_layers:
            return "No UVs found", 0
        
        # Get image
        image = bpy.data.images.get(input_image)
        if not image:
            return f"Image '{input_image}' missing", 0
        
        width, height = image.size
        total_pixels = width * height
        
        # Automatic downsampling based on image size
        downsampling = 1
        if total_pixels > 4_000_000:  # > ~2K
            downsampling = 2
        if total_pixels > 16_000_000:  # > ~4K
            downsampling = 4
        if total_pixels > 64_000_000:  # > ~8K
            downsampling = 8
        
        # Get selected faces
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        selected_faces = [f for f in bm.faces if f.select]
        
        if not selected_faces:
            return "No faces selected", 0
        
        # Prepare downsampled grid
        ds_width = ceil(width / downsampling)
        ds_height = ceil(height / downsampling)
        coverage = np.zeros((ds_height, ds_width), dtype=bool)
        
        # Process each face
        for face in selected_faces:
            uvs = [loop[uv_layer].uv for loop in face.loops]
            x_coords = [int(uv.x * ds_width) for uv in uvs]
            y_coords = [int(uv.y * ds_height) for uv in uvs]
            
            # Bounding box
            min_x, max_x = max(0, min(x_coords)), min(ds_width-1, max(x_coords))
            min_y, max_y = max(0, min(y_coords)), min(ds_height-1, max(y_coords))
            
            # Local grid
            face_grid = np.zeros((max_y-min_y+1, max_x-min_x+1), dtype=bool)
            local_x = [x-min_x for x in x_coords]
            local_y = [y-min_y for y in y_coords]
            
            # Scanline fill
            for y in range(face_grid.shape[0]):
                intersections = []
                for i in range(len(uvs)):
                    j = (i+1)%len(uvs)
                    if local_y[i] < local_y[j]:
                        x1, y1 = local_x[i], local_y[i]
                        x2, y2 = local_x[j], local_y[j]
                    else:
                        x1, y1 = local_x[j], local_y[j]
                        x2, y2 = local_x[i], local_y[i]
                    if y1 <= y < y2:
                        x = x1 + (y-y1)*(x2-x1)/(y2-y1)
                        intersections.append(int(x))
                
                intersections.sort()
                for k in range(0, len(intersections), 2):
                    if k+1 < len(intersections):
                        x_start = intersections[k]
                        x_end = intersections[k+1]
                        face_grid[y, x_start:x_end+1] = True
            
            # Merge coverage
            coverage[min_y:max_y+1, min_x:max_x+1] |= face_grid
        
        pixel_count = np.sum(coverage) * (downsampling**2)
        return None, pixel_count
    
    def store_uv_bbox(self):
        """Stores the bounding box of selected UV faces"""
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return "No mesh selected", None
        
        mesh = obj.data
        if not mesh.uv_layers:
            return "No UVs found", None
        
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        selected_faces = [f for f in bm.faces if f.select]
        
        if not selected_faces:
            return "No faces selected", None
        
        # Get all UV coordinates from selected faces
        all_uvs = [loop[uv_layer].uv for face in selected_faces for loop in face.loops]
        u_coords = [uv.x for uv in all_uvs]
        v_coords = [uv.y for uv in all_uvs]
        
        bbox = (min(u_coords), min(v_coords), max(u_coords), max(v_coords))
        return None, bbox
    
    def adjust_bbox_to_even(self, bbox):
        """Make bounding box square"""
        min_u, min_v, max_u, max_v = bbox
        
        width = max_u - min_u
        height = max_v - min_v
        size = max(width, height)
        
        center_u = (min_u + max_u) / 2
        center_v = (min_v + max_v) / 2
        
        new_min_u = center_u - size / 2
        new_max_u = center_u + size / 2
        new_min_v = center_v - size / 2
        new_max_v = center_v + size / 2
        
        return (new_min_u, new_min_v, new_max_u, new_max_v)
    
    def calculate_scale_ratio(self, bbox):
        """Calculate how much of UV space the bbox occupies"""
        min_u, min_v, max_u, max_v = bbox
        width = max_u - min_u
        height = max_v - min_v
        
        # Use the larger dimension as the scale reference
        scale_reference = max(width, height)
        return scale_reference
    
    def restore_uv_layout(self, original_bbox, original_scale_ratio):
        """Scale new UVs by original ratio and place at original location"""
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return "No mesh selected"
        
        mesh = obj.data
        if not mesh.uv_layers:
            return "No UVs found"
        
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        selected_faces = [f for f in bm.faces if f.select]
        
        if not selected_faces:
            return "No faces selected"
        
        # Get current bbox and center
        all_uvs = [loop[uv_layer].uv for face in selected_faces for loop in face.loops]
        u_coords = [uv.x for uv in all_uvs]
        v_coords = [uv.y for uv in all_uvs]
        
        curr_min_u, curr_min_v, curr_max_u, curr_max_v = min(u_coords), min(v_coords), max(u_coords), max(v_coords)
        curr_center_u = (curr_min_u + curr_max_u) / 2
        curr_center_v = (curr_min_v + curr_max_v) / 2
        
        # Calculate current scale
        curr_width = curr_max_u - curr_min_u
        curr_height = curr_max_v - curr_min_v
        curr_scale = max(curr_width, curr_height)
        
        # Calculate scale ratio
        scale_ratio = original_scale_ratio / curr_scale if curr_scale > 0 else 1.0
        
        # Original center (from even bbox)
        orig_min_u, orig_min_v, orig_max_u, orig_max_v = original_bbox
        orig_center_u = (orig_min_u + orig_max_u) / 2
        orig_center_v = (orig_min_v + orig_max_v) / 2
        
        # Scale and reposition
        for face in selected_faces:
            for loop in face.loops:
                uv = loop[uv_layer]
                # Scale around current center
                uv.uv.x = curr_center_u + (uv.uv.x - curr_center_u) * scale_ratio
                uv.uv.y = curr_center_v + (uv.uv.y - curr_center_v) * scale_ratio
                # Move to original center
                uv.uv.x += (orig_center_u - curr_center_u)
                uv.uv.y += (orig_center_v - curr_center_v)
        
        bmesh.update_edit_mesh(mesh)
        return None

class RecOperator(bpy.types.Operator):
    bl_idname = "wm.rec_operator"
    bl_label = "Record"
    bl_description = "Change the current state of UV"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        obj = bpy.context.object
        pms_props = scene.pms_properties
        try:
            pms_props.original_canvas = context.scene.tool_settings.image_paint.canvas.name
        except:
            pass
        matching_objects = get_image_users(pms_props.input_image)
        if matching_objects:
            if bpy.context.selected_objects:
                if all(obj in matching_objects for obj in bpy.context.selected_objects):
                    pass
                else:
                    self.report({'ERROR'}, "Select a matching object!")
                    return {'CANCELLED'}
        if bpy.context.active_object.data.uv_layers.active is None:
            mesh = obj.data
            mesh.uv_layers.new(name="UVMap")

        pms_props.input_uv = bpy.context.active_object.data.uv_layers.active.name                   
        rename_uv(pms_props.input_image, obj)
        
                # Check if the input image and UV map exist
        if pms_props.input_image not in bpy.data.images:
            self.report({'ERROR'}, "Input image does not exist!")
            return {'CANCELLED'}
        if pms_props.input_uv not in obj.data.uv_layers:
            self.report({'ERROR'}, "Input UV map does not exist!")
            return {'CANCELLED'}

        # Check if any material has the image node with the input_image
        image_node_found = False
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree
                for node in node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name == pms_props.input_image:
                        image_node_found = True
                        break
        if not image_node_found:
            self.report({'ERROR'}, f"Image node with '{pms_props.input_image}' does not exist in any material")
            return {'CANCELLED'}
        bpy.context.object.data.uv_layers[pms_props.input_uv].active_render = True
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
        cleanup_temp_nodes(pms_props.temp_suffix, False)
        pms_props.mode_before_record = bpy.context.object.mode
        try:
            bpy.ops.image.save_all_modified()
        except:
            pass
        uvmap_copy_ref = Record(pms_props.input_image, pms_props.input_uv, pms_props.temp_suffix, pms_props.checkpoint_suffix)
        pms_props.uvmap_copy_ref = uvmap_copy_ref.name   
        bpy.ops.object.mode_set(mode='EDIT')
        pms_props.safe_to_run = 1
        pms_props.lock = False
        try:
            bpy.ops.image.save_all_modified()
        except:
            pass
        
        #Store Selection, clear for all others and then restore for active
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh_selection = {}
        mesh = obj.data
        mesh_selection[obj.name] = {
            'verts': [v.select for v in mesh.vertices],
            'edges': [e.select for e in mesh.edges],
            'faces': [f.select for f in mesh.polygons]
    }
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for obj7 in matching_objects:             
            obj7.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        if pms_props.auto_unwrap == True and len(matching_objects) == 1:
            if pms_props.auto_unwrap_algo_smart == False:
                try:
                    if any(p.select for p in mesh.polygons):
                        bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', margin=0.001)
                        
                        bm = bmesh.from_edit_mesh(mesh)
                        uv_layer = bm.loops.layers.uv.verify()
                        
                        # Get selected faces
                        selected_faces = [face for face in bm.faces if face.select]
                        originally_hidden_faces = [face.index for face in bm.faces if face.hide]
                        bpy.ops.mesh.reveal()

                        # Calculate total 3D area of selected faces
                        selected_area = 0.0
                        # Calculate triangle count of selected faces
                        triangle_count = 0
                        
                        for face in selected_faces:
                            selected_area += face.calc_area()
                            triangle_count += len(face.verts) - 2  # n-gon has n-2 triangles
                        
                        # Calculate scale factor based on both area and triangle count
                        base_scale = 0.08

                        # Combine area and triangle count for scaling
                        area_percentage = selected_area / 1 
                        area_percentage = min(10, area_percentage)
                        triangle_percentage = triangle_count / 10 

                        # Add percentages to base scale
                        scale_factor = base_scale + (area_percentage + triangle_percentage) / 100

                        # Clamp to maximum 1.0
                        scale_factor = min(1.0, scale_factor)
                        print(base_scale)
                        print(f"Base: {base_scale:.3f}, Area %: {area_percentage:.1f}, Triangle %: {triangle_percentage:.1f}, Final: {scale_factor:.3f}")
                        
                        print(f"Selected area: {selected_area:.4f}, Triangles: {triangle_count}, Scale: {base_scale:.4f}")
                        
                        for face in selected_faces:
                            for loop in face.loops:
                                loop[uv_layer].uv *= scale_factor * pms_props.base_scale
                    
                        bmesh.update_edit_mesh(mesh)
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.uv.pack_islands(udim_source='CUSTOM_REGION', rotate=False, scale=False, margin_method='ADD', margin=0.0010, shape_method='CONVEX', merge_overlap=False)

                        if pms_props.input_image:
                            self.pixel_snap_selected(bm, uv_layer, pms_props.input_image) 

                        for face in bm.faces:
                            if face.index in originally_hidden_faces:
                                face.hide_set(True)

                        bmesh.update_edit_mesh(mesh)
                                                                    
                except:
                    print("No active face selection")
                    pass
            else:
                bm = bmesh.from_edit_mesh(mesh)
                uv_layer = bm.loops.layers.uv.verify()
                bpy.ops.mesh.select_all(action='SELECT')
                selected_faces = [face for face in bm.faces if face.select]
                originally_hidden_faces = [face.index for face in bm.faces if face.hide]
                bpy.ops.mesh.reveal()               
                bpy.ops.uv.smart_project(angle_limit=0, island_margin=0.0010)
                for face in selected_faces:
                    for loop in face.loops:
                        loop[uv_layer].uv *= 0.2
                if pms_props.input_image:
                    self.pixel_snap_selected(bm, uv_layer, pms_props.input_image) 
                for face in bm.faces:
                    if face.index in originally_hidden_faces:
                        face.hide_set(True)
                bmesh.update_edit_mesh(mesh)
                bpy.ops.mesh.mark_seam(clear=True)

        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        for i, v in enumerate(mesh.vertices):
            v.select = mesh_selection[obj.name]['verts'][i]
        for i, e in enumerate(mesh.edges):
            e.select = mesh_selection[obj.name]['edges'][i]
        for i, f in enumerate(mesh.polygons):
            f.select = mesh_selection[obj.name]['faces'][i]
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}

    def pixel_snap_selected(self, bm, uv_layer, image_name):
        """Pixel snap selected faces to the grid"""
        # Get the image
        image = bpy.data.images.get(image_name)
        if not image:
            print(f"Image '{image_name}' not found for pixel snapping")
            return
        
        # Get image dimensions
        width, height = image.size
        if width == 0 or height == 0:
            print("Image has invalid dimensions")
            return
        
        # Get selected faces
        selected_faces = [face for face in bm.faces if face.select]
        if not selected_faces:
            return
        
        # Snap all selected UVs to pixel grid
        for face in selected_faces:
            for loop in face.loops:
                uv = loop[uv_layer]
                # Convert to pixel coordinates, snap, convert back to UV coordinates
                uv.uv.x = round(uv.uv.x * width) / width
                uv.uv.y = round(uv.uv.y * height) / height  

class StopOperator(bpy.types.Operator):
    bl_idname = "wm.stop_operator"
    bl_label = "Stop"
    bl_description = "Apply the final state of UV and adapt the texture"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        #check for selected object(s)
        existing_selection = [obj for obj in bpy.context.selected_objects]
        if existing_selection == []:
            self.report({'ERROR'}, "No object selected (as yellow)")
            return {'CANCELLED'}
        #safety checks
        pms_props.safe_to_run += 1
        if pms_props.lock  == False:
            # Check if the input image and UV map exist
            if (pms_props.input_image not in bpy.data.images or
                pms_props.input_uv not in bpy.context.object.data.uv_layers or
                pms_props.input_uv + pms_props.temp_suffix not in bpy.context.object.data.uv_layers):
                self.report({'ERROR'}, "DATA OR NODES MISSING!")
                pms_props.lock = True
                cleanup_temp_nodes(pms_props.temp_suffix, False)
                cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
                bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
                pms_props.safe_to_run = 0
                return {'CANCELLED'}
            
            #proceed
            for uv_temp in bpy.context.object.data.uv_layers:
                if uv_temp.name == pms_props.input_uv + pms_props.temp_suffix:
                    bpy.context.object.data.uv_layers.active = uv_temp
            bpy.ops.object.mode_set(mode='OBJECT')

            if pms_props.safe_to_run == 2:
                try:
                    try:
                        bpy.ops.image.save_all_modified()
                    except:
                        pass
                    Stop(pms_props.input_image, pms_props.input_uv, pms_props.temp_suffix, pms_props.uvmap_copy_ref, False, "DIFFUSE", "", alpha=False, interpolation_override=pms_props.interpolations)
                except Exception as e:
                    print(f"Error stopping: {e}")
            else:
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_image)
                pms_props.safe_to_run = 0
                self.report({'ERROR'}, "STRUCTURE COMPROMISED")
            cleanup_temp_nodes(pms_props.temp_suffix, False)
            cleanup_temp_data(pms_props.temp_suffix, pms_props.input_image)
            bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
            for uv in bpy.context.object.data.uv_layers:
                if uv.name == pms_props.input_uv:
                    bpy.context.object.data.uv_layers.active = uv 
            pms_props.lock = True   
            pms_props.safe_to_run = 0
            pms_props.uv_adjust_happened = False
        if pms_props.auto_flush_alpha:
            bpy.ops.wm.pms_flush_alpha()
        try:
            bpy.ops.image.save_all_modified()
        except:
            pass
        self.report({'INFO'}, "Bake complete!")
        try:
            img = bpy.data.images.get(pms_props.original_canvas)
            context.scene.tool_settings.image_paint.canvas = img
        except:
            pass
        return {'FINISHED'}

class UV_PT_PaintMeSurprised_CanvasPicker(bpy.types.Panel):
    bl_label = "Canvas Picker"
    bl_idname = "PAINTME_PT_simple_canvas_picker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PaintMeSurprised"
    
    @classmethod 
    def poll(cls, context):
        pms_props = context.scene.pms_properties
        return (context.object and 
                context.object.type == 'MESH' and pms_props.enable_canvas_picker)
    
    def draw(self, context):
        layout = self.layout
        
        # 1. Get all images from the object's materials
        images = []
        obj = context.object
        
        for mat_slot in obj.material_slots:
            if mat_slot.material:
                mat = mat_slot.material
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            if node.image not in images:
                                images.append(node.image)
        
        # 2. Show current canvas
        ip = context.scene.tool_settings.image_paint
        current = ip.canvas if hasattr(ip, 'canvas') else None

        if hasattr(context.scene, 'pms_properties'):
            pms_props = context.scene.pms_properties

        box_k = layout.box()

        box_4 = box_k.box()
        row = box_4.row()
        if pms_props.paint_both == True:
            row.alert = True
            row.label(text=":", icon="NORMALS_FACE")
            row.operator("wm.paint_both_sides", text="", icon="CHECKBOX_HLT")
        else:
            row.alert = False
            row.label(text=":", icon="NORMALS_FACE")
            row.operator("wm.paint_both_sides", text="", icon="CHECKBOX_DEHLT")
            
        if pms_props.isolate_happened:
            row.alert = True
            row.label(text=":", icon="FACE_MAPS")
            row.operator("mesh.split_selected_faces", text="", icon="CHECKBOX_HLT")
        else:
            row.alert = False
            row.label(text=":", icon="FACE_MAPS")
            row.operator("mesh.split_selected_faces", text="", icon="CHECKBOX_DEHLT")
        box_h = box_k.box()
        box_h.prop(pms_props, 'auto_flush_image', text='Cloak', icon="GHOST_ENABLED")
        box_h.prop(pms_props, 'auto_merge', text='Auto Bake Cloak')
        row = box_k.row()
        row.operator("wm.bake_self_emit", text="Apply as layer", icon="TPAINT_HLT")
        row = box_k.row()
        if pms_props.auto_merge:
            row.operator("wm.pms_flush_image", 
                                            text="Bake to Linked", 
                                            icon='DECORATE_LIBRARY_OVERRIDE')
        else:
            row.operator("wm.pms_flush_image", 
                                            text="Wipe Cloak", 
                                            icon='GHOST_DISABLED')
               

        box2 = box_k.box()
        # 3. Show images as buttons with clear buttons
        if len(images) != 0:
            
            row = box2.row()
            row.label(text="Image Nodes:", icon="NODE")
            
            # Get the cloak image name from properties
            cloak_image_name = ""
            if hasattr(context.scene, 'pms_properties'):
                cloak_image_name = getattr(pms_props, 'auto_flush_image', "")
                linked_image = getattr(pms_props, 'input_image', "")
                        
            for img in images:
                row = box2.row()
                # Split row into two parts: select button and clear button
                split = row.split(factor=0.85)  # 80% for select, 20% for clear
                
                # Left side: Select button
                left_row = split.row()
                if img == current and context.scene.tool_settings.image_paint.mode == 'IMAGE' and context.object.mode == 'TEXTURE_PAINT':
                    left_row.alert = True
                    left_row.operator("paintme.select_this_canvas", 
                                text=img.name, 
                                
                                emboss=False).image_name = img.name
                else:
                    left_row.operator("paintme.select_this_canvas", 
                                    text=img.name, 
                                    ).image_name = img.name
                
                # Right side: Clear button (only if this is the cloak image)
                right_row = split.row()
                if img == current and context.scene.tool_settings.image_paint.mode == 'IMAGE' and img.name == cloak_image_name:
                    if pms_props.auto_merge == False:
                        right_row.operator("wm.pms_flush_image", 
                                        text="", 
                                        icon='GHOST_DISABLED')
                    else:
                        right_row.operator("wm.pms_flush_image", 
                                        text="", 
                                        icon='DECORATE_LIBRARY_OVERRIDE')
                elif img.name == cloak_image_name:
                    # Empty space for alignment
                    right_row.label(text="", icon="GHOST_ENABLED")
                    right_row.active = False
                elif img.name == linked_image:
                    right_row.label(text="", icon="RESTRICT_INSTANCED_OFF")
                    right_row.active = False
                else:
                    # Empty space for alignment
                    right_row.label(text="", icon="IMAGE_DATA") 
                    right_row.active = False                   
        else:
            box2.label(text="No images in material", icon='INFO')

class PAINTME_OT_select_this_canvas(bpy.types.Operator):
    bl_idname = "paintme.select_this_canvas"
    bl_label = "Set as Paint Canvas"
    
    image_name: bpy.props.StringProperty()
    
    def execute(self, context):
        img = bpy.data.images.get(self.image_name)
        if img:
            bpy.ops.object.mode_set(mode="TEXTURE_PAINT")
            context.scene.tool_settings.image_paint.canvas = img
            context.scene.tool_settings.image_paint.mode = 'IMAGE'
        return {'FINISHED'}    

class UV_PT_PaintMeSurprised_ColorPicker(bpy.types.Panel):
    bl_idname = "UV_PT_PaintMeSurprised_picker"
    bl_label = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PaintMeSurprised'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        pms_props = context.scene.pms_properties
        try:
            return ((context.object.mode == 'TEXTURE_PAINT' or context.object.mode == 'VERTEX_PAINT') and pms_props.enable_color_picker)
        except:
            return None

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="Color Picker")

    def draw(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        layout = self.layout
        error = 0
        if bpy.context.object.mode == 'TEXTURE_PAINT' or bpy.context.object.mode == 'VERTEX_PAINT':
            # Get the node reference

            tool_settings = context.scene.tool_settings
            unified_settings = tool_settings.image_paint.unified_paint_settings
            brush = context.tool_settings.image_paint.brush
            
            row = layout.row()
            row.prop(pms_props, "picker_type", text="Target", emboss=True)
            if pms_props.picker_type == 'brush':
                box = layout.box()
                row = box.row()
                if unified_settings.use_unified_color:
                    row.template_color_picker(unified_settings, "color", value_slider=True)
                    row = box.row()
                    row.prop(unified_settings, "color", text="")
                    row.prop(unified_settings, "use_unified_color", text="", icon="BRUSHES_ALL")
                    row.operator("brush.invert_color_keep_value", text="", icon="GESTURE_ROTATE")
                else:
                    if brush:
                        row.template_color_picker(brush, "color", value_slider=True)
                        row = box.row()
                        row.prop(brush, "color", text="")
                        row.prop(unified_settings, "use_unified_color", text="", icon="BRUSHES_ALL")
                        row.operator("brush.invert_color_keep_value", text="", icon="GESTURE_ROTATE")
            else:            
                material = context.scene.pms_properties.target_material
                if material and material.node_tree:
                    node = material.node_tree.nodes.get(pms_props.node_name)
                    if node:
                        try:
                            vector_input = node.inputs[pms_props.input_target]
                        except:
                            error = 1
                else:
                    error = 2
                        
                box = layout.box()
                row = box.row()
                row.prop(pms_props, "target_material", text="")
                row = box.row()
                row.prop(pms_props, "node_name", text="Node")
                row = box.row()
                row.prop(pms_props, "input_target", text="")
                #row = box.row()
                if error == 2:
                        row.alert = True
                        row.label(text=" ", icon='UNLINKED')
                        row = box.row()
                        row.label(text="Select a material!", icon='ERROR')
                else:
                    try:
                        if error == 0:
                            if vector_input and node.inputs[pms_props.input_target].type == 'VECTOR':
                                row.label(text=node.inputs[pms_props.input_target].name, icon='LINKED')
                            else:
                                row.label(text=node.inputs[pms_props.input_target].name, icon='UNLINKED')
                        else:
                            row.alert = True
                            row.label(text=" ", icon='UNLINKED')
                            row = box.row()
                            row.label(text="Out of inputs!", icon='ERROR')
                    except:
                        row.alert = True
                        row.label(text=" ", icon='UNLINKED')
                        row = box.row()
                        row.label(text="Node not found!", icon='ERROR')

                try:
                    if vector_input and node.inputs[pms_props.input_target].type == 'VECTOR':
                        row = box.row(align=True)
                        row.label(text="Order:", icon='OPTIONS')
                        boxz = row.box()  
                        if pms_props.toggle_order:
                            boxz.prop(pms_props, "toggle_order", text="Yellow", toggle=True, emboss=False)
                        else:
                            boxz.prop(pms_props, "toggle_order", text="Magenta", toggle=True, emboss=False)  
                        

                        # Individual RGB sliders
                        if pms_props.toggle_order:
                            col = box.column(align=True)  # Use aligned column
                            col.prop(vector_input, "default_value", text="Red", index=0, slider=True)
                            col.prop(vector_input, "default_value", text="Green", index=1, slider=True)
                            col.prop(vector_input, "default_value", text="Blue", index=2, slider=True)
                        else:
                            col = box.column(align=True)  # Use aligned column
                            col.prop(vector_input, "default_value", text="Red", index=0, slider=True)
                            col.prop(vector_input, "default_value", text="Blue", index=2, slider=True)
                            col.prop(vector_input, "default_value", text="Green", index=1, slider=True)
                    else:
                        row = box.row()
                        row.label(text="Not a vector input!", icon='ERROR')
                except:
                    pass
            row = layout.row()
            row.prop(brush, "use_accumulate", text="Airbrush")
            row.prop(brush, "use_alpha", text="Alpha")
        else:
            row = layout.row()
            row.label(text="Not in Texture or Vertex Paint mode!")

class UV_PT_PaintMeSurprised_CameraPicker(bpy.types.Panel):
    bl_idname = "UV_PT_PaintMeSurprised_PolygonArtTools"
    bl_label = ""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PaintMeSurprised'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        pms_props = context.scene.pms_properties
        try:
            return (pms_props.enable_camera_picker)
        except:
            return None

    def draw_header(self, context):
        layout = self.layout
        layout.label(text="Camera Picker")

    def draw(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        layout = self.layout
        row=layout.row()
        row.label(text='Camera:')
        row.prop(pms_props, 'camera_name', text='')
        row=layout.row()
        row.operator('paintme.flip_camera', text='Flip Camera')
        
class PAINTME_OT_use_camera(bpy.types.Operator):
    bl_idname = "paintme.flip_camera"
    bl_label = "Flip the Camera"
        
    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties        
        cam = bpy.data.objects.get(pms_props.camera_name)
        if cam and cam.type == 'CAMERA':
            if cam.scale[0] != -1:
                cam.scale[0] = -1
            else:
                cam.scale[0] = 1
        else:
            pass
        return {'FINISHED'}    

class UV_PT_PaintMeSurprised(bpy.types.Panel):
    bl_idname = "UV_PT_PaintMeSurprised"
    bl_label = "PaintMeSurprised"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PaintMeSurprised'

    def draw(self, context):
        obj = bpy.context.object
        layout = self.layout
        scene = context.scene
        pms_props = scene.pms_properties
        matching_objects = list(set(get_image_users(str(pms_props.input_image))))
        checkpoint_image = str(pms_props.input_image) + pms_props.checkpoint_suffix

        box = layout.box()
        row = box.row(align=True)
        row.operator("wm.pms_show_settings", text="Settings", icon="PREFERENCES") 

        if obj is not None:

            is_selected_match = False
            if any(obj in matching_objects for obj in bpy.context.selected_objects):
                is_selected_match = True

            if all(obj.type == 'MESH' for obj in bpy.context.selected_objects) and obj.type == 'MESH':

                if pms_props.safe_to_run == 0 and checkpoint_image in bpy.data.images:
                    row.operator("wm.reload_operator", text="", icon="PACKAGE", emboss=True)
                else:
                    row.label(text="", icon="UGLYPACKAGE")               

                col = box.column(align=True)
                row = col.row(align=True)
                row.prop(pms_props, "input_image", icon='RESTRICT_INSTANCED_OFF')
                row.operator("wm.focus_on_image", text="", icon="SELECT_SET")
                col = box.column(align=True)
                row = col.row(align=True)
                if pms_props.show_linked:
                    row.operator("wm.pms_set_linked", text="", icon="DOWNARROW_HLT", emboss=False)
                else:
                    row.operator("wm.pms_set_linked", text="", icon="RIGHTARROW", emboss=False)
                row.label(text=" Linked: "+str(len(matching_objects)))
                if is_selected_match:
                    row.operator("wm.focus_on_iu", text="", icon="SELECT_SET")
                else:
                    row = row.row()
                    row.enabled = False
                    row.operator("wm.focus_on_iu", text="", icon="SELECT_SET")
                
                temp_uv = pms_props.input_uv + pms_props.checkpoint_suffix
                if pms_props.show_linked:
                    col = layout.column()
                    for obj5 in matching_objects:
                        col.label(text=obj5.name, icon="OBJECT_DATA")
                    row = layout.row()
                    if matching_objects:
                        if bpy.context.selected_objects:
                            if is_selected_match:
                                row.alert = True
                                row.label(text="Selection:")
                                row.label(text=bpy.context.selected_objects[0].name, icon="OBJECT_DATA")
                            else:
                                row.alert = True
                                row.label(text="Selection:")
                                row.label(text="---", icon="ERROR")
                        else:
                            row.alert = True
                            row.label(text="Selection:")
                            row.label(text="---", icon="ERROR")
                    else:
                        row.label(text="No match found!", icon="ERROR")
                box3 = layout.box()
                row = box3.row()  
                shortcut = False
                if pms_props.safe_to_run == 0:
                    col = row.column()
                    col.alert = False
                    if is_selected_match:
                        col.enabled = True
                        if pms_props.auto_unwrap == True and len(matching_objects) == 1:
                            col.operator("wm.retexel_operator", text="Retexelize", icon="MOD_REMESH")
                        else:
                            col.operator("wm.rec_operator", text="Change UV", icon="UV")
                    else:
                        col.enabled = False
                        col.operator("wm.rec_operator", text="Select a linked object")
                    row = box3.row()
                    if is_selected_match:
                        if pms_props.auto_unwrap == True and len(matching_objects) == 1:
                            row.label(text="Auto Unwrap mode", icon="INFO")
                        elif pms_props.auto_unwrap == True and len(matching_objects) != 1:
                            row.label(text="Auto Unwrap denied!", icon="ERROR")
                            row = layout.row()
                            row.alert = True
                            row.label(text="Can't process multiple objects!")
                        else:
                            row.label(text="Ready", icon="INFO")
                    else:
                        row.label(text="Unavailable", icon="INFO")
                elif pms_props.safe_to_run == 1 and temp_uv in obj.data.uv_layers:
                    shortcut = True
                    col = row.column()
                    col.alert = True
                    col.operator("wm.stop_operator", text="Apply", icon="REC")
                    row.operator("wm.cleanup_operator", text="", icon="CANCEL")
                    row = box3.row(align=True)
                    row.label(text="UV Editing...", icon="INFO")                    
                else:   
                    col = row.column()
                    col.alert = False
                    row2 = row.row()
                    row2.operator("wm.recover_operator", text="Restart", icon="FILE_REFRESH")
                    row = box3.row(align=True)
                    row.alert = True
                    row.label(text="COMPROMISED", icon="ERROR")  

                row = box3.row()
                if (shortcut == True and pms_props.auto_unwrap == False) or shortcut == True and pms_props.auto_unwrap == True and len(matching_objects) != 1:
                    row.enabled = True
                else:
                    row.enabled = False                   
                if pms_props.input_image == "" or obj.mode != 'EDIT':
                    row.enabled = False
                row.operator("uv.layout_manager_pixel_check", text="Unwrap", icon="GROUP_UVS") 

                row = box3.row()
                if (shortcut == True and pms_props.auto_unwrap == False) or shortcut == True and pms_props.auto_unwrap == True and len(matching_objects) != 1:
                    row.enabled = True
                else:
                    row.enabled = False          
                row.operator("wm.request_pms", text="Match UV", icon="UV_SYNC_SELECT")
                if pms_props.uv_adjust_happened == True:
                    row.operator("wm.request_pms_cancel", text="", icon="CANCEL")
                if pms_props.enable_autounwrap:
                    row = box3.row() 
                    row.prop(pms_props, "auto_unwrap", text="Auto Unwrap Selected Faces")
                    if pms_props.auto_unwrap:
                        row = box3.row()
                        row.label(text="", icon="GRIP")
                        row.prop(pms_props, "auto_unwrap_algo_smart", text="Dissect")
                    row = box3.row()
                    if pms_props.auto_unwrap == True:
                        row.enabled = True
                    else:
                        row.enabled = False
                    row.label(text="Scale:")
                    row.prop(pms_props, "base_scale", text="")    

                if pms_props.enable_quickbake:
                    box = layout.box()
                    row = box.row()
                    if shortcut == True or (not bpy.context.selected_objects):
                        row.enabled = False
                    else:
                        row.enabled = True  

                    row.operator("wm.bake_emit_chain", text="Bake", icon="RENDER_STILL")             
                    row.prop(pms_props, "bake_type", text="")
                    row = box.row()
                    if pms_props.bake_type != "ALPHA":
                        row.label(text="Bake image:")
                        row.prop(pms_props, "input_image_emit", text="")
                    else:
                        row.label(text="Alpha (Color) mode")
                        row.operator("wm.pms_flush_alpha", text="", icon="BRUSH_DATA") 
       
            else:
                box = layout.box()
                row = box.row()
                box.label(text="Not a mesh object!", icon="ERROR")
        else:
            box = layout.box()
            row = box.row()
            box.label(text="No object is selected!", icon="ERROR")
            
classes = (
    PMS_Properties,
    SetLinked,
    UV_PT_PaintMeSurprised,
    UV_PT_PaintMeSurprised_ColorPicker,
    RecOperator,
    StopOperator,
    CleanupOperator,
    RecoverOperator,
    PaintBothSides,
    UV_reqest_cancel,
    Focus_on_Image,
    UV_request,
    BakeEmitChain,
    BakeSelfEmit,
    Select_all_image_users,
    RetexelOperator,
    UVLayoutManagerWithPixelCheck,
    ReloadOperator,
    BRUSH_OT_invert_color_keep_value,
    FlushAlpha,
    Show_settings_PMS,
    PAINTME_OT_select_this_canvas,
    UV_PT_PaintMeSurprised_CanvasPicker,
    ForceFlushCloak,
    MESH_OT_split_selected_faces,
    UV_PT_PaintMeSurprised_CameraPicker,
    PAINTME_OT_use_camera


)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pms_properties = bpy.props.PointerProperty(type=PMS_Properties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.pms_properties

if __name__ == "__main__":
    register()