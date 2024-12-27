TEMP_SUFFIX = "_temp_pms"
#change suffix here if conflicts with other addons
mode_before_record = None

bl_info = {
    "name": "PaintMeSurprised",
    "version": (1, 4, 2),
    "blender": (4, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > PaintMeSurprised",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
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
    global mode_before_record
    mode_before_record = bpy.context.object.mode
   
    #Set the image as the active image in the Image Editor
    image_og = bpy.data.images[og_tex_name]
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image_og
            break     

    uvmap_copy = copyUVMAP(current_active_uv)
    copy_texture = copyTexture(og_tex_name)
    #Record.copy_texture = copy_texture
    #Record.uvmap_copy = uvmap_copy

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
    global mode_before_record
    obj = bpy.context.object

    # Store the original interpolation of the og-tex image node
    og_tex_node = None
    for node in obj.active_material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image and node.image.name == og_tex_name:
            og_tex_node = node
            break
    if og_tex_node:
        original_interpolation = og_tex_node.interpolation

    try:
        # Change the interpolation to 'Closest'
        if og_tex_node:
            og_tex_node.interpolation = 'Closest'

        # Store the current render settings and switch to Cycles for baking
        original_render_engine = bpy.context.scene.render.engine
        original_margin_type = bpy.context.scene.render.bake.margin_type
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.render.bake.margin_type = 'EXTEND'

        # Perform the bake emit operation
        bpy.ops.object.bake(type='EMIT')

    finally:
        # Restore the original interpolation and render engine
        if og_tex_node:
            og_tex_node.interpolation = original_interpolation
        bpy.context.scene.render.engine = original_render_engine
        bpy.context.scene.render.bake.margin_type = original_margin_type

    # Copying textures
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

    if mode_before_record is not None:
        bpy.ops.object.mode_set(mode=mode_before_record)              

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

    # Set the original image node as the active selected
    if active_mat and active_mat.use_nodes:
        node_tree = active_mat.node_tree
        for node in node_tree.nodes:
            node.select = False
        for node in node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                image_node = node
                image_node.select = True
                node_tree.nodes.active = image_node


class CleanupOperator(bpy.types.Operator):
    bl_idname = "wm.cleanup_operator"
    bl_label = "Cancel"
    bl_description = "Drop the lenses"

    def execute(self, context):
        cleanup()
        bpy.ops.object.mode_set(mode=mode_before_record)
        context.scene.lock = True
        return {'FINISHED'}

class UV_PT_PaintMeSurprised(bpy.types.Panel):
    bl_idname = "UV_PT_PaintMeSurprised"
    bl_label = "PaintMeSurprised"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PaintMeSurprised'


    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "my_input")
        col.prop(scene, "my_input_uv")
        row = layout.row(align=True)
        if context.scene.lock:
            col = row.column()
            col.alert = False
            col.operator("wm.rec_operator", text="Record", icon="UV")
        else:
            col = row.column()
            col.alert = True
            col.operator("wm.stop_operator", text="Stop", icon="REC")
            row.operator("wm.cleanup_operator", text="", icon="CANCEL")

class RecOperator(bpy.types.Operator):
    bl_idname = "wm.rec_operator"
    bl_label = "Record"
    bl_description = "Record the current state of UV"

    def execute(self, context):
        if context.scene.lock:
            input_text = context.scene.my_input
            input_uv = context.scene.my_input_uv
            
                # Check if the input image and UV map exist
        if input_text not in bpy.data.images:
            self.report({'ERROR'}, "Input image does not exist")
            return {'CANCELLED'}
        obj = bpy.context.object
        if input_uv not in obj.data.uv_layers:
            self.report({'ERROR'}, "Input UV map does not exist")
            return {'CANCELLED'}
        
        # Check if the active material has the image node with the my_input and is connected to the output material
        material = bpy.context.object.active_material
        if material and not material.use_nodes:
            self.report({'ERROR'}, "Active material does not have a node tree")
            return {'CANCELLED'}

        image_node = None
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_text:
                image_node = node
                break
        if image_node is None:
            self.report({'ERROR'}, f"Image node with '{input_text}' does not exist in the active material")
            return {'CANCELLED'}

        cleanup()
        Record(input_text, input_uv)
        bpy.ops.object.mode_set(mode='EDIT')
        context.scene.lock = False        
        return {'FINISHED'}

class StopOperator(bpy.types.Operator):
    bl_idname = "wm.stop_operator"
    bl_label = "Stop"
    bl_description = "Apply the final state of UV and update the texture"

    def execute(self, context):
        if context.scene.lock == False:
            input_text = context.scene.my_input
            input_uv = context.scene.my_input_uv
            
            # Check if the input image and UV map exist
            if (input_text not in bpy.data.images or
                input_uv not in bpy.context.object.data.uv_layers or
                input_text + TEMP_SUFFIX not in bpy.data.images):
                self.report({'ERROR'}, f"Image '{input_text}' or UV map '{input_uv}' or temp image '{input_text + TEMP_SUFFIX}' does not exist")
                context.scene.lock = True
                return {'CANCELLED'}
            
            bpy.ops.object.mode_set(mode='OBJECT')
            Stop(input_text, input_uv)
            cleanup()
            bpy.ops.object.mode_set(mode=mode_before_record)
            context.scene.lock = True
        return {'FINISHED'}

def register():
    bpy.utils.register_class(UV_PT_PaintMeSurprised)
    bpy.utils.register_class(RecOperator)
    bpy.utils.register_class(StopOperator)
    bpy.utils.register_class(CleanupOperator)
    Scene = bpy.types.Scene
    Scene.my_input = bpy.props.StringProperty(name="Image")
    Scene.my_input_uv = bpy.props.StringProperty(name="UV")
    Scene.lock = bpy.props.BoolProperty(default=True)

def unregister():
    for cls in (UV_PT_PaintMeSurprised, RecOperator, StopOperator, CleanupOperator):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.my_input
    del bpy.types.Scene.my_input_uv
    del bpy.types.Scene.lock

if __name__ == "__main__":
    register()

print