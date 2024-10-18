#globals
mode_before_record = "EDIT"
image_node_of_og_tex = None
image_node_of_copy = None
uvnode_of_og_tex = None
uvnode_of_copy = None
original_connections = {}

bl_info = {
    "name": "PaintMeSurprised",
    "version": (1, 6, 1),
    "blender": (4, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > PaintMeSurprised",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
}

import bpy
import numpy as np

class PMS_Properties(bpy.types.PropertyGroup):
    input_image : bpy.props.StringProperty(name="Image", default="", description="Image to use")
    input_uv : bpy.props.StringProperty(name="UV", default="", description="UV to use")
    lock : bpy.props.BoolProperty(name="Lock", default=True)
    safe_to_run : bpy.props.IntProperty(name="safe_to_run", default=0)
    temp_suffix : bpy.props.StringProperty(name="temp_suffix", default="_temp_pms")
    checkpoint_suffix : bpy.props.StringProperty(name="checkpoint_suffix", default="_pms_checkpoint")
    mix_method : bpy.props.BoolProperty(name="Always Mix", default=True)
    image_mode : bpy.props.EnumProperty(name="Image Algorithm", description="Pixel exchange method between temporary and original images", items=[("none", "Automatic", ""),("mix", "Always Mix", ""), ("transfer", "Always Transfer", "")], default="none")

def np_array_from_image(img_name):
    img = bpy.data.images[img_name]
    return np.array(img.pixels[:])

def mix_images(img_name1, img_name2):
    print(f"Mixing {img_name1} and {img_name2}")
    pixels1 = np_array_from_image(img_name1)
    pixels2 = np_array_from_image(img_name2)
    mixed_pixels = np.where(pixels1 == 0, pixels2, pixels1)
    print(mixed_pixels)
    return mixed_pixels

def get_matching_objects(input_uv, input_image):
    matching_objects = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH':  # only consider mesh objects
            uv_layer = obj.data.uv_layers.get(input_uv)
            if uv_layer and any(mat.material and mat.material.node_tree and any(node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image for node in mat.material.node_tree.nodes) for mat in obj.material_slots):
                matching_objects.append(obj)
    return matching_objects

def get_image_users(image_name):    
    users = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH':  # only consider mesh objects
            for mat in obj.material_slots:
                if mat.material and mat.material.node_tree and any(node.type == 'TEX_IMAGE' and node.image and node.image.name == image_name for node in mat.material.node_tree.nodes):
                    users.append(obj)
    return users

def copyTexture(input_image, suffix):
    original_texture = bpy.data.images.get(input_image)
    copy_texture = original_texture.copy()
    copy_texture.name = f"{input_image}{suffix}"
    return copy_texture

def copyUVMAP(input_uv, suffix, input_image):
    for obj in get_matching_objects(input_uv, input_image):
        uvmap_copy = obj.data.uv_layers.new()
        uvmap_copy.name = f"{input_uv}{suffix}"
    return uvmap_copy
    
def Record(input_image, input_uv, temp_suffix, checkpoint_suffix):
    obj = bpy.context.object
    global mode_before_record
    #emptying globals
    global original_connections
    global image_node_of_og_tex
    global image_node_of_copy
    global uvnode_of_og_tex
    global uvnode_of_copy
    original_connections = {}
    image_node_of_og_tex = None
    image_node_of_copy = None
    uvnode_of_og_tex = None
    uvnode_of_copy = None

    #Store the mode before record
    mode_before_record = bpy.context.object.mode

    # Set the image as the active image in the Image Editor
    image_og = bpy.data.images[input_image]
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image_og
            break

    # Make copy of image and uv data
    clone = copyTexture(input_image, checkpoint_suffix)
    transfer_pixels(input_image, clone.name)
    copyUVMAP(input_uv, checkpoint_suffix, input_image)
    uvmap_copy = copyUVMAP(input_uv, temp_suffix, input_image)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':  # Ensure the object is a mesh
            for uv_map in obj.data.uv_layers:
                if uv_map.name == uvmap_copy.name:
                    obj.data.uv_layers.active = uv_map
                    break  # Exit the loop once the UV map is found
    copy_texture = copyTexture(input_image, temp_suffix)

    # Get node tree ref from all materials
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree

            # Find og image node and store reference
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                    image_node_of_og_tex = node

                    # Make new image node for copy and store reference
                    image_node_of_copy = node_tree.nodes.new(type="ShaderNodeTexImage")
                    image_node_of_copy.name = f"im{temp_suffix}"
                    image_node_of_copy.image = bpy.data.images.get(copy_texture.name)
                    # Make new uvmap nodes for each and store reference
                    uvnode_of_og_tex = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_og_tex.name = f"uvog{temp_suffix}"
                    uvnode_of_og_tex.uv_map = input_uv
                    uvnode_of_copy = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_copy.name = f"uvcop{temp_suffix}"
                    uvnode_of_copy.uv_map = uvmap_copy.name
                    break

def connectNodesForBaking(input_image, temp_suffix):
    # Connections:
    global original_connections
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree
            #Store original material output
            material_output = node_tree.nodes.get("Material Output")
            original_connections[node_tree] = None
            for link in material_output.inputs["Surface"].links:
                original_connections[node_tree] = link.from_node
                break

            # Connect og image nodes to material output
            image_og_node = None
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

def transfer_pixels(source, target):
    source_image = bpy.data.images.get(source)
    og_tex = bpy.data.images.get(target)
    og_tex.pixels = source_image.pixels[:]

def transfer_uv(source, target):
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            source_uv = obj.data.uv_layers.get(source)
            target_uv = obj.data.uv_layers.get(target)
            if source_uv and target_uv:
                for loop in obj.data.loops:
                    target_uv.data[loop.index].uv = source_uv.data[loop.index].uv

def Stop(input_image, input_uv, temp_suffix, mix_method):
    obj = bpy.context.object
    matching_objects = get_matching_objects(input_uv, input_image)
    selected_objects = bpy.context.selected_objects
    image_users = get_image_users(input_image)
    # Store the original interpolation of the image nodes with og_tex_name
    original_interpolations = {}
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_image:
                    original_interpolations[node] = node.interpolation

    try:           
        # Change the interpolation to 'Closest'
        for node, original_interpolation in original_interpolations.items():
            node.interpolation = 'Closest'

        # Store the current render settings and switch to Cycles for baking
        original_render_engine = bpy.context.scene.render.engine
        original_margin_type = bpy.context.scene.render.bake.margin_type
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.render.bake.margin_type = 'EXTEND'
        # Perform the bake emit operation
        bpy.ops.object.bake(type='EMIT')
    except Exception as e:
        print(f"Error baking: {e}")
    finally:
        # Restore the original interpolation and render engine
        for node, original_interpolation in original_interpolations.items():
            node.interpolation = original_interpolation
        bpy.context.scene.render.engine = original_render_engine
        bpy.context.scene.render.bake.margin_type = original_margin_type

    # Get the image data from the selected node
    try:
        if mix_method == 'transfer':
            transfer_pixels(input_image + temp_suffix, input_image)
        elif mix_method == 'mix':
            mixed_image = mix_images(input_image, input_image + temp_suffix)
            mixed_image = mix_images(input_image + temp_suffix, input_image)
            print(mixed_image)
            image_D = bpy.data.images[input_image]
            image_D.pixels = mixed_image.tolist()
        elif (len(matching_objects) == 1 or
            (all(obj in matching_objects for obj in selected_objects) and
            all(obj in selected_objects for obj in matching_objects) and
            all(user in matching_objects for user in image_users) and
            all(user in selected_objects for user in image_users))):
            transfer_pixels(input_image + temp_suffix, input_image)
        elif (len(matching_objects) > 1 or
            any(obj not in matching_objects for obj in selected_objects) or
            any(user not in matching_objects for user in image_users)):
            mixed_image = mix_images(input_image, input_image + temp_suffix)
            mixed_image = mix_images(input_image + temp_suffix, input_image)
            print(mixed_image)
            image_D = bpy.data.images[input_image]
            image_D.pixels = mixed_image.tolist()
        else:
            mixed_image = mix_images(input_image, input_image + temp_suffix)
            mixed_image = mix_images(input_image + temp_suffix, input_image)
            print(mixed_image)
            image_D = bpy.data.images[input_image]
            image_D.pixels = mixed_image.tolist()

        if uvnode_of_copy is not None:
            transfer_uv(uvnode_of_copy.uv_map, input_uv)
        else:
            print("UV Node of Copy missing!")
    except:
        print("ERROR: DIDNT FIND ANYTHING")
    if input_image in bpy.data.images:
        image = bpy.data.images[input_image]
    
    # Set the image as the active image in the Image Editor
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image
            break

    # Restore original connections
    if mode_before_record is not None:
        bpy.ops.object.mode_set(mode=mode_before_record)     

    # Set the UV map as the active UV map
    for obj in matching_objects:
        now_active = obj.data.uv_layers.get(input_uv)
        obj.data.uv_layers.active = now_active

def restore_connections():
    global original_connections

            # Restore original connections
    for node_tree, original_connection in original_connections.items():
        if original_connection:
            material_output = node_tree.nodes.get("Material Output")
            node_tree.links.new(original_connection.outputs[0], material_output.inputs["Surface"])
        else:
            pass

def cleanup_temp_nodes(temp_suffix):
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
    if image_node_of_og_tex is not None:
        image_node_of_og_tex.select = True
        material.node_tree.nodes.active = image_node_of_og_tex

def cleanup_temp_data(temp_suffix, input_uv, input_image):
    # Remove unneeded images
    for image in bpy.data.images:
    # Check if the image name contains '_temp'
        if temp_suffix in image.name:
        # Remove the image
            bpy.data.images.remove(image)

    # Remove unneeded UV maps
    matching_objects = get_matching_objects(input_uv, input_image)
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
    matching_objects = get_matching_objects(input_uv, input_image)
    for obj in matching_objects:
        for uv_map in obj.data.uv_layers:
            if checkpoint_suffix in uv_map.name:
                obj.data.uv_layers.remove(uv_map)

class CleanupOperator(bpy.types.Operator):
    bl_idname = "wm.cleanup_operator"
    bl_label = "Cancel"
    bl_description = "Drop the lenses"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        cleanup_temp_nodes(pms_props.temp_suffix)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        #bpy.ops.uv.paste()
        bpy.ops.object.mode_set(mode=mode_before_record)
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
    bl_options = {'INTERNAL'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        pms_props. safe_to_run += 1
        cleanup_temp_nodes(pms_props.temp_suffix)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        #bpy.ops.uv.paste()
        pms_props.safe_to_run = 0
        pms_props.lock = True
        return {'FINISHED'}

class ReloadOperator(bpy.types.Operator):
    bl_idname = "wm.reload_operator"
    bl_label = "Reload"
    bl_description = "Reload the previous state of uv and texture"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        pms_props = context.scene.pms_properties
        pms_props. safe_to_run += 1
        obj = bpy.context.object   
        cleanup_temp_nodes(pms_props.temp_suffix)
        cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        if checkpoint_image in bpy.data.images:
            transfer_pixels(pms_props.input_image + pms_props.checkpoint_suffix, pms_props.input_image)
        for uv_map in obj.data.uv_layers:
            if pms_props.checkpoint_suffix in uv_map.name:
                bpy.ops.object.mode_set(mode='OBJECT')
                transfer_uv(pms_props.input_uv + pms_props.checkpoint_suffix, pms_props.input_uv)
                bpy.ops.object.mode_set(mode=mode_before_record)
        remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
        pms_props.safe_to_run = 0

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
        checkpoint_image = pms_props.input_image + pms_props.checkpoint_suffix
        checkpoint_uv = pms_props.input_uv + pms_props.checkpoint_suffix
        matching_objects = get_matching_objects(pms_props.input_uv, pms_props.input_image)
        selected_objectos = bpy.context.selected_objects
        image_users = get_image_users(pms_props.input_image)
        
        if pms_props.safe_to_run == 0 and (checkpoint_uv in obj.data.uv_layers or checkpoint_image in bpy.data.images):
            row = layout.row(align=True)
            row.operator("wm.reload_operator", text="Last Checkpoint", icon="FILE_REFRESH")
        else:
            layout.separator(factor=3.4)

        col = layout.column(align=True)
        col.prop(pms_props, "input_image")
        col.prop(pms_props, "input_uv")
        row = layout.row(align=True)
        row.label(text="Linked: "+str(len(matching_objects)))
        row.label(text="Image users: "+str(len(image_users)))
        
        temp_image = pms_props.input_image + pms_props.checkpoint_suffix
        temp_uv = pms_props.input_uv + pms_props.checkpoint_suffix

        col = layout.column()
        for obj5 in matching_objects:
            #if obj not in bpy.context.selected_objects or obj5 != bpy.context.active_object:
            col.label(text=obj5.name, icon="OBJECT_DATA")
        row = layout.row()
        if matching_objects:
            if bpy.context.selected_objects:
                if any(obj in matching_objects for obj in bpy.context.selected_objects):
                    row.alert = True
                    row.label(text="Selection:")
                    row.label(text=obj.name, icon="OBJECT_DATA")
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
        if pms_props.safe_to_run == 0:
            col = row.column()
            col.alert = False
            col.operator("wm.rec_operator", text="Record", icon="UV")
            row = layout.row(align=True)
            if any(obj in matching_objects for obj in bpy.context.selected_objects):
                row.label(text="Ready", icon="INFO")
            else:
                row.label(text="Unavailable", icon="INFO")
        elif pms_props.safe_to_run == 1 and (temp_image in bpy.data.images and temp_uv in obj.data.uv_layers):
            col = row.column()
            col.alert = True
            col.operator("wm.stop_operator", text="Stop", icon="REC")
            row.operator("wm.cleanup_operator", text="", icon="CANCEL")
            row = layout.row(align=True)
            row.label(text="Recording...", icon="INFO")
        else:   
            col = row.column()
            col.alert = False
            row.operator("wm.recover_operator", text="Restart", icon="FILE_REFRESH")
            row = layout.row(align=True)
            row.label(text="COMPROMISED", icon="ERROR")
        row = layout.row()
        if pms_props.image_mode == 'transfer':
            row.label(text="Transfer (A->B)", icon="RENDERLAYERS")
        elif pms_props.image_mode == 'mix':
            row.label(text="Mixing (A+B)", icon="RENDERLAYERS")
        elif (len(matching_objects) == 1 or
            (all(obj in matching_objects for obj in selected_objectos) and
            all(obj in selected_objectos for obj in matching_objects) and
            all(user in matching_objects for user in image_users) and
            all(user in selected_objectos for user in image_users))):
            row.label(text="Transfer (A->B)", icon="RENDERLAYERS")
        elif (len(matching_objects) > 1 or
            any(obj not in matching_objects for obj in selected_objectos) or
            any(user not in matching_objects for user in image_users)):
            row.label(text="Mixing (A+B)", icon="RENDERLAYERS")
        else:
            row.label(text="Mixing (A+B)", icon="RENDERLAYERS")
        row = layout.row()
        row.prop(pms_props, "image_mode", text="")
               
class RecOperator(bpy.types.Operator):
    bl_idname = "wm.rec_operator"
    bl_label = "Record"
    bl_description = "Record the current state of UV"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        scene = context.scene
        pms_props = scene.pms_properties
        matching_objects = get_matching_objects(pms_props.input_uv, pms_props.input_image)
        can_run = False
        if matching_objects:
            if bpy.context.selected_objects:
                if all(obj in matching_objects for obj in bpy.context.selected_objects):
                    can_run = True
        if not can_run: 
            self.report({'ERROR'}, "Select a matching object!")
            return {'CANCELLED'}   
                # Check if the input image and UV map exist
        if pms_props.input_image not in bpy.data.images:
            self.report({'ERROR'}, "Input image does not exist!")
            return {'CANCELLED'}
        obj = bpy.context.object
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
        cleanup_temp_nodes(pms_props.temp_suffix)
        Record(pms_props.input_image, pms_props.input_uv, pms_props.temp_suffix, pms_props.checkpoint_suffix)
        bpy.ops.image.save_all_modified()
        bpy.ops.object.mode_set(mode='EDIT')
        pms_props.safe_to_run = 1
        pms_props.lock = False   
        return {'FINISHED'}

class StopOperator(bpy.types.Operator):
    bl_idname = "wm.stop_operator"
    bl_label = "Stop"
    bl_description = "Apply the final state of UV and update the texture"
    bl_options = {'INTERNAL'}

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
                pms_props.input_image + pms_props.temp_suffix not in bpy.data.images or
                pms_props.input_uv + pms_props.temp_suffix not in bpy.context.object.data.uv_layers or
                not all(any(node.name in mat.node_tree.nodes for mat in bpy.data.materials if mat.node_tree)
                        for node in [uvnode_of_copy, uvnode_of_og_tex, image_node_of_copy, image_node_of_og_tex])):
                self.report({'ERROR'}, "DATA OR NODES MISSING!")
                pms_props.lock = True
                cleanup_temp_nodes(pms_props.temp_suffix)
                cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
                bpy.ops.object.mode_set(mode=mode_before_record)
                pms_props.safe_to_run = 0
                return {'CANCELLED'}
            
            #proceed
            for uv_temp in bpy.context.object.data.uv_layers:
                if uv_temp.name == pms_props.input_uv + pms_props.temp_suffix:
                    bpy.context.object.data.uv_layers.active = uv_temp
            bpy.ops.object.mode_set(mode='OBJECT')
            connect_nodes_success = False
            try:
                connectNodesForBaking(pms_props.input_image, pms_props.temp_suffix)
                connect_nodes_success = True
            except Exception as e:
                self.report({'ERROR'}, f"Error connecting nodes for baking: {e}")
            if connect_nodes_success and pms_props.safe_to_run == 2:
                try:
                    Stop(pms_props.input_image, pms_props.input_uv, pms_props.temp_suffix, pms_props.image_mode)
                except Exception as e:
                    print(f"Error stopping: {e}")
            else:
                remove_checkpoint_data(pms_props.checkpoint_suffix, pms_props.input_uv, pms_props.input_image)
                pms_props.safe_to_run = 0
                self.report({'ERROR'}, "STRUCTURE COMPROMISED")
            cleanup_temp_nodes(pms_props.temp_suffix)
            cleanup_temp_data(pms_props.temp_suffix, pms_props.input_uv, pms_props.input_image)
            bpy.ops.object.mode_set(mode=mode_before_record)
            for uv in bpy.context.object.data.uv_layers:
                if uv.name == pms_props.input_uv:
                    bpy.context.object.data.uv_layers.active = uv 
            pms_props.lock = True   
            pms_props.safe_to_run = 0
        return {'FINISHED'}

classes = (
    PMS_Properties,
    UV_PT_PaintMeSurprised,
    RecOperator,
    StopOperator,
    CleanupOperator,
    ReloadOperator,
    RecoverOperator,
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