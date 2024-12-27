#globals
image_node_of_og_tex_pms = None
imgae_node_of_copy_pms = None
uvnode_of_og_tex_pms = None
uvnode_of_copy_pms = None
original_connections_pms = {}

bl_info = {
    "name": "PaintMeSurprised",
    "version": (1, 9, 11),
    "blender": (4, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > PaintMeSurprised",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
}

import bpy

class PMS_Properties(bpy.types.PropertyGroup):
    input_image : bpy.props.StringProperty(name="Image", default="", description="Image to use")
    input_uv : bpy.props.StringProperty(name="UV", default="", description="UV to use")
    lock : bpy.props.BoolProperty(name="Lock", default=True)
    safe_to_run : bpy.props.IntProperty(name="safe_to_run", default=0)
    temp_suffix : bpy.props.StringProperty(name="temp_suffix", default="_temp_pms")
    checkpoint_suffix : bpy.props.StringProperty(name="checkpoint_suffix", default="_pms_checkpoint")
    image_mode : bpy.props.EnumProperty(name="Image Algorithm", description="Pixel exchange method between temporary and original images", items=[("none", "Automatic", ""),("mix", "Mixing", ""), ("transfer", "Transfer", "")], default="none")
    toggle_clean_preview: bpy.props.BoolProperty(name="Lock", default=False)
    paint_both: bpy.props.BoolProperty(name="Paint Both Sides", default=False)
    previous_interpolations: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    previous_overlay_state: bpy.props.BoolProperty(default=True)
    uv_adjust : bpy.props.FloatVectorProperty(default=(1.0, 1.0, 1.0))
    mode_before_record : bpy.props.StringProperty(default="EDIT")
    uv_adjust_happened : bpy.props.BoolProperty(default=False)
    uvmap_copy_ref: bpy.props.StringProperty(default="")
    margin_size: bpy.props.EnumProperty(name="Bake Margin", description="Extends the baked result as a post process", items=[("0", "0", ""),("1", "1", ""), ("2", "2", ""), ("4", "4", "")], default="2")
    bake_type: bpy.props.EnumProperty(name="Bake Type", description="Bake type", items=[("EMIT", "Color", "Bake RGB only."),("NORMAL", "Normals", "Bake a normal map"), ("COMBINED", "Render", "Bake a combined render according to cycles settings")], default="EMIT")

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

def connectNodesForBaking(input_image, temp_suffix, is_bakefullchain):
    # Connections:
    
    global original_connections_pms
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree
            #Store original material output
            material_output = node_tree.nodes.get("Material Output")
            original_connections_pms[node_tree] = None
            for link in material_output.inputs["Surface"].links:
                original_connections_pms[node_tree] = link.from_node
                break

            # Connect og image nodes to material output
            image_og_node = None
            if is_bakefullchain == False:
                for node in node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                        image_og_node = node
                        break

                if image_og_node is not None:
                    node_tree.links.new(image_og_node.outputs["Color"], material_output.inputs["Surface"])

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

def Stop(input_image, input_uv, temp_suffix, uvmap_copy_name, margin_size, is_bakefullchain, bake_type):

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


    if is_bakefullchain == False:
        matching_objects = get_image_users(input_image)
        copy_texture = copyTexture(input_image, temp_suffix)

        bpy.ops.object.select_all(action='DESELECT')
        for member in matching_objects:
            if member.hide_get() is True:
                member.hide_set(False)
                og_hidden = member
            member.select_set(True)

       # Get node tree ref from all materials
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree

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
                            
                        # Make new image node for copy and store reference
                        imgae_node_of_copy_pms = node_tree.nodes.new(type="ShaderNodeTexImage")
                        imgae_node_of_copy_pms.name = f"im{temp_suffix}"
                        imgae_node_of_copy_pms.image = bpy.data.images.get(copy_texture.name)
                        break
    else:
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree
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
            node.interpolation = 'Closest'

        # Store the current render settings and switch to Cycles for baking
        original_render_engine = bpy.context.scene.render.engine
        original_margin_type = bpy.context.scene.render.bake.margin_type
        original_margine_size = bpy.context.scene.render.bake.margin
        original_samples = bpy.context.scene.cycles.samples
        original_bounces = bpy.context.scene.cycles.max_bounces
        original_denoise = bpy.context.scene.cycles.use_denoising
        bpy.context.scene.render.engine = 'CYCLES'
        if is_bakefullchain == True:
            if bake_type == 'COMBINED':
                pass
            else:
                bpy.context.scene.cycles.max_bounces = 0
                bpy.context.scene.cycles.samples = 1
                bpy.context.scene.cycles.use_denoising = False
        else:
            bpy.context.scene.cycles.use_denoising = False
            bpy.context.scene.cycles.samples = 1
            bpy.context.scene.cycles.max_bounces = 0
            
        bpy.context.scene.render.bake.margin_type = 'EXTEND'
        bpy.context.scene.render.bake.margin = int(margin_size)
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
        bpy.context.scene.cycles.use_denoising = original_denoise

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

        bpy.ops.object.select_all(action='DESELECT')
        for obj in matching_objects:
            try:
                og_hidden.hide_set(True)
            except:
                pass
            og_obj.select_set(True)
        bpy.context.view_layer.objects.active = og_obj

    uvnode_of_copy_pms = None
    uvnode_of_og_tex_pms = None
    imgae_node_of_copy_pms = None

def restore_connections():
    global original_connections_pms

            # Restore original connections
    for node_tree, original_connection in original_connections_pms.items():
        if original_connection:
            material_output = node_tree.nodes.get("Material Output")
            node_tree.links.new(original_connection.outputs[0], material_output.inputs["Surface"])
        else:
            pass

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

def cleanup_temp_data(temp_suffix, input_uv, input_image):
    # Remove unneeded images
    for image in bpy.data.images:
    # Check if the image name contains '_temp'
        if temp_suffix in image.name:
        # Remove the image
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

def remove_checkpoint_data(checkpoint_suffix, input_uv, input_image):
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
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
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
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image, True)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        pms_props.safe_to_run = 0
        pms_props.lock = True
        return {'FINISHED'}

class ReloadOperator(bpy.types.Operator):
    bl_idname = "wm.reload_operator"
    bl_label = "Reload"
    bl_description = "Reload the previous state of uv and texture"
    bl_options = {'UNDO'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        pms_props. safe_to_run += 1
        obj = bpy.context.object   
        cleanup_temp_nodes(pms_props.temp_suffix, False)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image, True)
        for uv_map in obj.data.uv_layers:
            if pms_props.checkpoint_suffix in uv_map.name:
                bpy.ops.object.mode_set(mode='OBJECT')
                transfer_uv(pms_props.input_uv + pms_props.checkpoint_suffix, pms_props.input_uv)
                bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        pms_props.safe_to_run = 0

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
    bl_label = "Select Linked"
    bl_description = "Select all objects using the input image"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        image_users = get_image_users(pms_props.input_image)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for obj in image_users:
            #obj.hide_set(False)
            obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class BakeEmitChain(bpy.types.Operator):
    bl_idname = "wm.bake_emit_chain"
    bl_label = "Bake Emission Chain"
    bl_description = "Bakes shader to selected image node."
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        can_run = False
        mat = bpy.context.object.active_material
        mode_before = bpy.context.object.mode
        bpy.ops.paint.texture_paint_toggle()
        bpy.ops.object.mode_set(mode=mode_before)

        try:
            for idx, img in enumerate(mat.texture_paint_images):
                if idx == mat.paint_active_slot:
                    active_image = img.name
        except:
            self.report({'ERROR'}, "No image node found on this object!")
            return {'CANCELLED'}
        if bpy.context.selected_objects:
                can_run = True
        if not can_run: 
            self.report({'ERROR'}, "Select an object!")
            return {'CANCELLED'}
        obj = bpy.context.object
        for mat in obj.data.materials:
            if mat.use_nodes:
                active_node = mat.node_tree.nodes.active
                try:
                    if active_node and active_node.type == 'TEX_IMAGE' and active_node.image and active_node.image.name == pms_props.input_image or active_image == pms_props.input_image:
                        self.report({'ERROR'}, "Input image is PROTECTED! Material named <"+ str(mat.name) + "> tried to bake to it. Select another image node or remove it from the material.")
                        return {'CANCELLED'}
                except:
                    self.report({'ERROR'}, "No active image node found on this material!")
                    return {'CANCELLED'}
        cleanup_temp_data("_bakedfullchain", pms_props.input_uv, pms_props.input_image)
        bpy.ops.object.mode_set(mode='OBJECT')
        Stop(pms_props.input_image, pms_props.input_uv, "_bakedfullchain", pms_props.uvmap_copy_ref, pms_props.margin_size, True, pms_props.bake_type)
        cleanup_temp_nodes(pms_props.temp_suffix, True)
        cleanup_temp_nodes("_bakedfullchain", True)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)   
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
    bl_description = "Calculate the difference in UV size from the last checkpoint. Only useful after Resize while recording"
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

class CleanPreviewOperator(bpy.types.Operator):
    bl_idname = "wm.clean_preview"
    bl_label = "Clean Preview"
    bl_description = "Turn off overlays and set image interpolation to Linear"
    bl_options = {'UNDO'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        if pms_props.toggle_clean_preview == False:
            pms_props.previous_interpolations.clear()
            for mat in bpy.data.materials:
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            item = pms_props.previous_interpolations.add()
                            item.name = node.name
                            item["interpolation"] = node.interpolation
                            node.interpolation = 'Linear'
            pms_props.previous_overlay_state = context.space_data.overlay.show_overlays
            context.space_data.overlay.show_overlays = False
            pms_props.toggle_clean_preview = True
        elif pms_props.toggle_clean_preview == True:
            for mat in bpy.data.materials:
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            for item in pms_props.previous_interpolations:
                                if item.name == node.name:
                                    node.interpolation = item["interpolation"]
                                    break
            context.space_data.overlay.show_overlays = pms_props.previous_overlay_state
            pms_props.toggle_clean_preview = False
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

class RecOperator(bpy.types.Operator):
    bl_idname = "wm.rec_operator"
    bl_label = "Record"
    bl_description = "Record the current state of UV"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        obj = bpy.context.object
        pms_props = scene.pms_properties
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
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
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
            #obj7.hide_set(False)               
            obj7.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
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

class StopOperator(bpy.types.Operator):
    bl_idname = "wm.stop_operator"
    bl_label = "Stop"
    bl_description = "Apply the final state of UV and update the texture"
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
                cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
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
                    Stop(pms_props.input_image, pms_props.input_uv, pms_props.temp_suffix, pms_props.uvmap_copy_ref, pms_props.margin_size, False, "EMIT")
                except Exception as e:
                    print(f"Error stopping: {e}")
            else:
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
                pms_props.safe_to_run = 0
                self.report({'ERROR'}, "STRUCTURE COMPROMISED")
            cleanup_temp_nodes(pms_props.temp_suffix, False)
            cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
            bpy.ops.object.mode_set(mode=pms_props.mode_before_record)
            for uv in bpy.context.object.data.uv_layers:
                if uv.name == pms_props.input_uv:
                    bpy.context.object.data.uv_layers.active = uv 
            pms_props.lock = True   
            pms_props.safe_to_run = 0
            pms_props.uv_adjust_happened = False
        try:
            bpy.ops.image.save_all_modified()
        except:
            pass
        self.report({'INFO'}, "Bake complete!") 
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
        checkpoint_image = str(pms_props.input_image) + pms_props.checkpoint_suffix
        checkpoint_uv = pms_props.input_uv + pms_props.checkpoint_suffix
        matching_objects = list(set(get_image_users(str(pms_props.input_image))))

        if obj is not None:
            if all(obj.type == 'MESH' for obj in bpy.context.selected_objects) and obj.type == 'MESH':
                box = layout.box()
                row = box.row(align=True)
                if pms_props.safe_to_run == 0 and (checkpoint_uv in obj.data.uv_layers or checkpoint_image in bpy.data.images):
                    row.enabled = True
                else:
                    row.enabled = False
                row.operator("wm.reload_operator", text="Last Checkpoint", icon="FILE_REFRESH")

                col = box.column(align=True)
                row = col.row(align=True)
                row.prop(pms_props, "input_image")
                row.operator("wm.focus_on_image", text="", icon="SELECT_SET")
                row = box.row(align=True)
                row.label(text="Linked: "+str(len(matching_objects)))
                row.operator("wm.focus_on_iu", text="", icon="SELECT_SET")
                
                temp_uv = pms_props.input_uv + pms_props.checkpoint_suffix

                col = layout.column()
                for obj5 in matching_objects:
                    col.label(text=obj5.name, icon="OBJECT_DATA")
                row = layout.row()
                if matching_objects:
                    if bpy.context.selected_objects:
                        if any(obj in matching_objects for obj in bpy.context.selected_objects):
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
                row = layout.row()
                shortcut = False
                if pms_props.safe_to_run == 0:
                    col = row.column()
                    col.alert = False
                    if any(obj in matching_objects for obj in bpy.context.selected_objects):
                        col.enabled = True
                        col.operator("wm.rec_operator", text="Record", icon="UV")
                    else:
                        col.enabled = False
                        col.operator("wm.rec_operator", text="Select a linked object")
                    row = layout.row()
                    if any(obj in matching_objects for obj in bpy.context.selected_objects):
                        row.label(text="Ready", icon="INFO")
                    else:
                        row.label(text="Unavailable", icon="INFO")
                elif pms_props.safe_to_run == 1 and temp_uv in obj.data.uv_layers:
                    shortcut = True
                    col = row.column()
                    col.alert = True
                    col.operator("wm.stop_operator", text="Stop", icon="REC")
                    row.operator("wm.cleanup_operator", text="", icon="CANCEL")
                    row = layout.row(align=True)
                    row.label(text="Recording...", icon="INFO")
                else:   
                    col = row.column()
                    col.alert = False
                    row2 = row.row()
                    row2.operator("wm.recover_operator", text="Restart", icon="FILE_REFRESH")
                    row = layout.row(align=True)
                    row.label(text="COMPROMISED" + str(pms_props.safe_to_run), icon="ERROR")
                row = layout.row()
                row.label(text="Margin:")
                row.prop(pms_props, "margin_size", text="")

                box = layout.box()
                row = box.row()
                if shortcut == True or not bpy.context.selected_objects:
                    row.enabled = False
                else:
                    row.enabled = True                 
                row.operator("wm.bake_emit_chain", text="Bake", icon="RENDER_STILL")               
                row.prop(pms_props, "bake_type", text="")
                row = box.row()    
                if shortcut == True:
                    row.enabled = True
                else:
                    row.enabled = False          
                row.operator("wm.request_pms", text="Match UV", icon="UV_SYNC_SELECT")
                if pms_props.uv_adjust_happened == True:
                    row.operator("wm.request_pms_cancel", text="", icon="CANCEL")
                row = box.row()
                
                if pms_props.paint_both == True:
                    row.alert = True
                    row.label(text=":", icon="NORMALS_FACE")
                    row.operator("wm.paint_both_sides", text="", icon="CHECKBOX_HLT")
                else:
                    row.alert = False
                    row.label(text=":", icon="NORMALS_FACE")
                    row.operator("wm.paint_both_sides", text="", icon="CHECKBOX_DEHLT")
                    
                if pms_props.toggle_clean_preview == True:
                    row.alert = True
                    row.label(text=":", icon="OVERLAY")
                    row.operator("wm.clean_preview", text="", icon="CHECKBOX_HLT")
                    
                else:
                    row.alert = False
                    row.label(text=":", icon="OVERLAY")
                    row.operator("wm.clean_preview", text="", icon="CHECKBOX_DEHLT")

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
    UV_PT_PaintMeSurprised,
    RecOperator,
    StopOperator,
    CleanupOperator,
    ReloadOperator,
    RecoverOperator,
    CleanPreviewOperator,
    PaintBothSides,
    UV_reqest_cancel,
    Focus_on_Image,
    UV_request,
    BakeEmitChain,
    Select_all_image_users,
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