#globals
TEMP_SUFFIX = "_temp_pms"
mode_before_record = "EDIT"
image_node_of_og_tex = None
image_node_of_copy = None
uvnode_of_og_tex = None
uvnode_of_copy = None
original_connections = {}

bl_info = {
    "name": "PaintMeSurprised",
    "version": (1, 4, 5),
    "blender": (4, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > PaintMeSurprised",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
}

import bpy

def copyTexture(arg1):
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
    print(mode_before_record)

    # Set the image as the active image in the Image Editor
    image_og = bpy.data.images[og_tex_name]
    for area in bpy.context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            area.spaces.active.image = image_og
            break

    # Make copy of image and uv data
    uvmap_copy = copyUVMAP(current_active_uv)
    copy_texture = copyTexture(og_tex_name)

    # Get node tree ref from all materials
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree

            # Find og image node and store reference
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == og_tex_name:
                    image_node_of_og_tex = node

            # Make new image node for copy and store reference
                    image_node_of_copy = node_tree.nodes.new(type="ShaderNodeTexImage")
                    image_node_of_copy.name = f"im{TEMP_SUFFIX}"
                    image_node_of_copy.image = bpy.data.images.get(copy_texture.name)

                    # Make new uvmap nodes for each and store reference
                    uvnode_of_og_tex = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_og_tex.name = f"uvog{TEMP_SUFFIX}"
                    uvnode_of_og_tex.uv_map = current_active_uv
                    uvnode_of_copy = node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvnode_of_copy.name = f"uvcop{TEMP_SUFFIX}"
                    uvnode_of_copy.uv_map = uvmap_copy.name
                    print(uvmap_copy.name, uvnode_of_copy.uv_map)

def connectNodesForBaking(og_tex_name):
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
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == og_tex_name:
                    image_og_node = node


            node_tree.links.new(image_og_node.outputs["Color"], material_output.inputs["Surface"])
            # Connect uv nodes to image nodes
            uv_og_node = node_tree.nodes.get(f"uvog{TEMP_SUFFIX}")
            image_copy_node = node_tree.nodes.get(f"im{TEMP_SUFFIX}")
            uv_copy_node = node_tree.nodes.get(f"uvcop{TEMP_SUFFIX}")
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

def Stop(og_tex_name, current_active_uv):
    obj = bpy.context.object

    # Store the original interpolation of the image nodes with og_tex_name
    original_interpolations = {}
    for material in bpy.data.materials:
        if material.use_nodes:
            node_tree = material.node_tree
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image and node.image.name == og_tex_name:
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

    finally:
        # Restore the original interpolation and render engine
        for node, original_interpolation in original_interpolations.items():
            node.interpolation = original_interpolation
        bpy.context.scene.render.engine = original_render_engine
        bpy.context.scene.render.bake.margin_type = original_margin_type

    # Get the image data from the selected node
    source_image = bpy.data.images.get(og_tex_name + TEMP_SUFFIX)
    og_tex = bpy.data.images.get(og_tex_name)
    og_tex.pixels = source_image.pixels[:]
   
    #copying uv      
    # Ensure the object is a mesh
    if obj.type == 'MESH':
        # Get the UV maps
        source_uv = obj.data.uv_layers.get(uvnode_of_copy.uv_map)
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

    # Set the UV map as the active UV map
    obj.data.uv_layers.active = target_uv

def cleanup(current_active_uv):
    global original_connections

        # Restore original connections
    for node_tree, original_connection in original_connections.items():
        if original_connection:
            material_output = node_tree.nodes.get("Material Output")
            node_tree.links.new(original_connection.outputs[0], material_output.inputs["Surface"])

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
    for material in bpy.data.materials:
        if material and material.use_nodes:
            nodes = material.node_tree.nodes
            for node in list(nodes):
                if TEMP_SUFFIX in node.name:
                    nodes.remove(node)

    # Set the original image node as the active selected
    if image_node_of_og_tex is not None:
        image_node_of_og_tex.select = True
        material.node_tree.nodes.active = image_node_of_og_tex

class CleanupOperator(bpy.types.Operator):
    bl_idname = "wm.cleanup_operator"
    bl_label = "Cancel"
    bl_description = "Drop the lenses"

    def execute(self, context):
        cleanup(context.scene.my_input_uv)
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

        # Check if any material has the image node with the my_input
        image_node_found = False
        for material in bpy.data.materials:
            if material.use_nodes:
                node_tree = material.node_tree
                for node in node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.name == input_text:
                        image_node_found = True
                        break
        if not image_node_found:
            self.report({'ERROR'}, f"Image node with '{input_text}' does not exist in any material")
            return {'CANCELLED'}
        bpy.context.object.data.uv_layers[input_uv].active_render = True
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
                input_text + TEMP_SUFFIX not in bpy.data.images or
                input_uv + TEMP_SUFFIX not in bpy.context.object.data.uv_layers):
                self.report({'ERROR'}, f"Image '{input_text}' or UV map '{input_uv}' or temp image '{input_text + TEMP_SUFFIX}' or temp UV map '{input_uv + TEMP_SUFFIX}' does not exist")
                context.scene.lock = True
                cleanup(input_uv)
                return {'CANCELLED'}
            
            #proceed
            bpy.ops.object.mode_set(mode='OBJECT')
            connectNodesForBaking(input_text)
            Stop(input_text, input_uv)
            cleanup(input_uv)
            bpy.ops.object.mode_set(mode=mode_before_record)
            for uv in bpy.context.object.data.uv_layers:
                if uv.name == input_uv:
                    bpy.context.object.data.uv_layers.active = uv 
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