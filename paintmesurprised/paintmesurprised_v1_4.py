TEMP_SUFFIX = "_temp_pms"
#change suffix here if conflicts with other addons

bl_info = {
    "name": "PaintMeSurprised v1.4",
    "blender": (4, 00, 0),
    "category": "3D View",
    "location": "3D View > Sidebar > Pain(t)killer",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
}

import bpy

def copyTexture(arg1):
    obj = bpy.context.object
    original_texture = bpy.data.images.get(arg1)
    copy_texture = original_texture.copy()
    copy_texture.name = f"{arg1}{TEMP_SUFFIX}"
    return copy_texture
    
def copyUVMAP(arg1):
    obj = bpy.context.object
    uvmap_copy = obj.data.uv_layers.new()
    uvmap_copy.name = f"{arg1}{TEMP_SUFFIX}"
    obj.data.uv_layers.active = uvmap_copy
    return uvmap_copy
    
def Record(og_tex_name, current_active_uv):
    # Check if the input image and UV map exist
    if og_tex_name not in bpy.data.images:
        print("Error: Input image does not exist")
        return
    obj = bpy.context.object
    if current_active_uv not in obj.data.uv_layers:
        print("Error: Input UV map does not exist")
        return

    uvmap_copy = copyUVMAP(current_active_uv)
    copy_texture = copyTexture(og_tex_name)
    Record.copy_texture = copy_texture
    Record.uvmap_copy = uvmap_copy

    material = bpy.context.object.active_material
    if material and not material.use_nodes:
        material.use_nodes = True
    node_tree = material.node_tree
    #make new node for copy
    image_node = node_tree.nodes.new(type="ShaderNodeTexImage")
    image_node.name = f"im{TEMP_SUFFIX}"
    image_node.image = bpy.data.images.get(copy_texture.name)
    #make new uvmapnodes for each
    uv_node_og = node_tree.nodes.new(type='ShaderNodeUVMap')
    uv_node_og.name = f"uvog{TEMP_SUFFIX}"
    uv_node_og.uv_map = current_active_uv
    uv_node_copy = node_tree.nodes.new(type='ShaderNodeUVMap')
    uv_node_copy.name = f"uvcop{TEMP_SUFFIX}"
    uv_node_copy.uv_map = uvmap_copy.name

    #connections
    #finding og:
    material_output = node_tree.nodes.get("Material Output")
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image and node.image.name == og_tex_name:
            node_tree.links.new(node.outputs["Color"], material_output.inputs["Surface"])
            node_tree.links.new(uv_node_og.outputs["UV"], node.inputs["Vector"])

           
    node_tree.links.new(uv_node_copy.outputs["UV"], image_node.inputs["Vector"])

    for node in node_tree.nodes:
            node.select = False
            
    image_node.select = True        
    node_tree.nodes.active = image_node
    
    
    
def Stop(og_tex_name, current_active_uv):
    obj = bpy.context.object
    
    # Perform the bake emit operation
    bpy.context.scene.render.engine = 'CYCLES'
    bpy.ops.object.bake(type='EMIT')

    #copying textures
    if obj.active_material:
        mat = obj.active_material
        nodes = mat.node_tree.nodes

    selected_node = None
    for node in nodes:
        if node.select and node.type == 'TEX_IMAGE':
            selected_node = node
            break

    if selected_node and selected_node.image:
            # Get the image data from the selected node
            source_image = selected_node.image
            og_tex = bpy.data.images.get(og_tex_name)
            og_tex.pixels = source_image.pixels[:]
    
        
#copying uv


    # Get the active object
    obj = bpy.context.active_object

    # Ensure the object has a material
    if obj.active_material is None:
        raise Exception("The active object does not have a material")

    # Get the active material
    material = obj.active_material

    # Get the node tree of the material
    nodes = material.node_tree.nodes

    # Find the selected image texture node
    selected_node = None
    for node in nodes:
        if node.select and node.type == 'TEX_IMAGE':
            selected_node = node
            break

    if selected_node is None:
        raise Exception("No image texture node is selected")

    # Find the UV Map node connected to the selected image texture node
    uv_map_node = None
    for link in selected_node.inputs['Vector'].links:
        if link.from_node.type == 'UVMAP':
            uv_map_node = link.from_node
            break
        
    obj = bpy.context.active_object
    print(uv_map_node and current_active_uv)
    # Ensure the object is a mesh
    if obj.type == 'MESH':
        # Get the UV maps
        source_uv = obj.data.uv_layers.get(uv_map_node.uv_map)
        target_uv = obj.data.uv_layers.get(current_active_uv)

        
        if source_uv and target_uv:
            # Copy UV data from source to target
            for loop in obj.data.loops:
                target_uv.data[loop.index].uv = source_uv.data[loop.index].uv
          
    
    if og_tex_name in bpy.data.images:
        image = bpy.data.images[og_tex_name]
    
    # Set the image as the active image in the Image Editor
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image
            break

def cleanup():
    # Remove unneeded images
    for image in bpy.data.images:
        # Check if the image name contains '_temp'
        if TEMP_SUFFIX in image.name:
            # Remove the image
            bpy.data.images.remove(image)

    # Get the active object
    obj = bpy.context.active_object
    # Remove unneeded UV maps
    for uv_map in obj.data.uv_layers:
        # Check if the UV map name contains '_temp'
        if TEMP_SUFFIX in uv_map.name:
            # Remove the UV map
            obj.data.uv_layers.remove(uv_map)

    # Remove unneeded nodes from all materials
    active_mat = obj.active_material
    if active_mat and active_mat.use_nodes:
        nodes = active_mat.node_tree.nodes
        for node in list(nodes):
            if TEMP_SUFFIX in node.name:
                nodes.remove(node) 


class PaintMeSurprised(bpy.types.Panel):
    bl_label = "PaintMeSurprised"
    bl_idname = "PT_PaintMeSurprised"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pain(t)killer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "my_input")
        col.prop(scene, "my_input_uv")

        layout.prop(scene, "lock")

        row = layout.row(align=True)
        if context.scene.lock:
            col = row.column()
            col.alert = False
            col.operator("wm.rec_operator", text="Record", icon="UV")
        else:
            col = row.column()
            col.alert = True
            col.operator("wm.stop_operator", text="Stop", icon="REC")

class RecOperator(bpy.types.Operator):
    bl_idname = "wm.rec_operator"
    bl_label = "Record"

    def execute(self, context):
        if context.scene.lock:
            input_text = context.scene.my_input
            input_uv = context.scene.my_input_uv
            
            # Check if the input image and UV map exist
            if input_text not in bpy.data.images or input_uv not in bpy.context.object.data.uv_layers:
                print("Error: Input image or UV map does not exist")
                return {'CANCELLED'}

            bpy.ops.object.mode_set(mode='EDIT')
            cleanup()
            Record(input_text, input_uv)
            context.scene.lock = False
        return {'FINISHED'}

class StopOperator(bpy.types.Operator):
    bl_idname = "wm.stop_operator"
    bl_label = "Stop"

    def execute(self, context):
        if context.scene.lock == False:
            input_text = context.scene.my_input
            input_uv = context.scene.my_input_uv
            
            # Check if the input image and UV map exist
            if input_text not in bpy.data.images or input_uv not in bpy.context.object.data.uv_layers:
                print("Error: Input image or UV map does not exist")
                return {'CANCELLED'}
            
            bpy.ops.object.mode_set(mode='OBJECT')
            Stop(input_text, input_uv)
            cleanup()
            bpy.ops.object.mode_set(mode='EDIT')
            context.scene.lock = True
        return {'FINISHED'}

def register():
    bpy.utils.register_class(PaintMeSurprised)
    bpy.utils.register_class(RecOperator)
    bpy.utils.register_class(StopOperator)
    Scene = bpy.types.Scene
    Scene.my_input = bpy.props.StringProperty(name="Image")
    Scene.my_input_uv = bpy.props.StringProperty(name="UV")
    Scene.lock = bpy.props.BoolProperty(name="Ready To Record ...", default=True)

def unregister():
    for cls in (PaintMeSurprised, RecOperator, StopOperator):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.my_input
    del bpy.types.Scene.my_input_uv
    del bpy.types.Scene.lock

if __name__ == "__main__":
    register()

