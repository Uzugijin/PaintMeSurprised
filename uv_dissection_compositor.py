bl_info = {
    "name": "UV Dissection Compositor",
    "version": (1, 0, 0),
    "blender": (5, 00, 0),
    "category": "UV",
    "location": "3D View > Sidebar > UVDC",
    "description": "Baking assist for TAM modeling",
    "author": "Uzugijin",
    "doc_url": "https://uzugijin.github.io/pages/tam.html"
} 

import bpy
import os
import bmesh

class UVDC_Properties(bpy.types.PropertyGroup):

    do_extend: bpy.props.BoolProperty(default=True)
    margin: bpy.props.IntProperty(default=10, min=0, max=10)   
    record_mode: bpy.props.BoolProperty(default=True)
    coll_list: bpy.props.BoolProperty(default=False)
    coll_listg: bpy.props.BoolProperty(default=False)
    object_mode: bpy.props.StringProperty(default="EDIT")
    autounwrap: bpy.props.BoolProperty(default=False)
    uv_scale_multiplier: bpy.props.FloatProperty(default=1.0, min=0.1, max=2, precision=1)
    uvdc_renderchain_menu_node_enable: bpy.props.BoolProperty(default=False)
    uvdc_renderchain_menu_node_image: bpy.props.StringProperty(default="")
    uvdc_renderchain_menu_node_name: bpy.props.StringProperty(default="")
    uvdc_renderchain_menu_node_input: bpy.props.StringProperty(default="")
    uvdc_renderchain_menu_node_restore: bpy.props.StringProperty(default="")

class UVDC_Properties_List(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()

def get_images_and_users(selected_objects):
    from collections import defaultdict
    
    # Convert single object to list if needed
    if not isinstance(selected_objects, (list, tuple, set)):
        selected_objects = [selected_objects]
    
    images = []
    users = []
    display = []

    # Cache: image -> list of objects that use it
    image_to_objects = defaultdict(list)
    
    # First, build a complete lookup of all image usage in the scene
    for scene_obj in bpy.context.scene.objects:
        for mat_slot in scene_obj.material_slots:
            if mat_slot.material:
                mat = mat_slot.material
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            image = node.image
                            if scene_obj not in image_to_objects[image]:
                                image_to_objects[image].append(scene_obj)
    
    # Now process selected objects and discover relationships
    objects_to_process = list(selected_objects)
    processed_objects = set()
    
    while objects_to_process:
        obj = objects_to_process.pop(0)
        
        if obj in processed_objects:
            continue
            
        processed_objects.add(obj)
        users.append(obj)
        
        # Get all images from this object
        obj_images = []
        for mat_slot in obj.material_slots:
            if mat_slot.material:
                mat = mat_slot.material
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            image = node.image
                            if image not in obj_images:
                                obj_images.append(image)
        
        # Add images to main list
        for image in obj_images:
            if image not in images and image not in display:
                if image.get('enable', True):
                    images.append(image)
                display.append(image)
            
            # Find all objects that use this image
            for related_obj in image_to_objects[image]:
                if (related_obj not in processed_objects and 
                    related_obj not in objects_to_process):
                    objects_to_process.append(related_obj)
    return images, users, display

class UV_Dissection_Compositor(bpy.types.Operator):
    bl_idname = "wm.uvdissectioncompositor"
    bl_label = "UV Dissection Compositor"
    bl_description = "..."
    bl_options = {'UNDO'}

    mode: bpy.props.IntProperty(default=0)
    #0 = Run
    #1 = Prepare
    #2 = Cancel
    #3 = Bake EEVEE
    #4 = AutoUnwrap
    #5 = Bake Renderchain

    def execute(self, context):        
        scene = context.scene
        uvdc_props = context.scene.uvdc_properties
        image_list, matching_objects, _ = get_images_and_users(context.object)
        original_selected = context.object
        og_hidden = []
        original_canvas = context.scene.tool_settings.image_paint.canvas.name
        uvdc_props.object_mode = context.object.mode

        if self.mode == 5 or self.mode == 3:
            errors = []
            if uvdc_props.uvdc_renderchain_menu_node_image == '':
                errors.append('No Image!')
                if len(errors) > 0:
                    self.report({'ERROR'}, f"{errors}")     
                    return {'CANCELLED'}   

        if self.mode == 1 or self.mode == 4:
            uvdc_props = context.scene.uvdc_properties
            uvdc_props.object_mode = context.object.mode

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')

            for obj in matching_objects:
                
                if obj.hide_get() is True:
                    obj.hide_set(False)
                    og_hidden.append(obj)
                obj.select_set(True)                
                if obj.type == 'MESH':
                    obj.data.uv_layers.active.name = "UVDC_UVMap"
                    temp_uv = obj.data.uv_layers.new()
                    temp_uv.name = "UVDC_UVMap_temp"
                    obj.data.uv_layers.active = temp_uv

            bpy.ops.object.mode_set(mode='EDIT')    
            uvdc_props.record_mode = False

            if self.mode == 4:
                try:
                    master_scale = uvdc_props.uv_scale_multiplier #default 1
                    mesh_selection = {}
                    mesh = original_selected.data
                    mesh_selection[original_selected.name] = {
                        'faces': [f.select for f in mesh.polygons]    
                    }
                    if any(p.select for p in mesh.polygons):

                        def restore():
                            bpy.ops.mesh.select_all(action='DESELECT')
                            bpy.ops.object.mode_set(mode='OBJECT')
                            for i, f in enumerate(mesh.polygons):
                                f.select = mesh_selection[original_selected.name]['faces'][i]
                            bpy.ops.object.mode_set(mode='EDIT')
                        restore()
                    
                        bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', margin=0.001)
                        bpy.ops.uv.pin(clear=False)
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.uv.pin(invert=True)
                        restore()
                              
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
                                loop[uv_layer].uv *= scale_factor * master_scale
                    
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.uv.pack_islands(udim_source='CUSTOM_REGION', rotate=False, scale=False, margin_method='ADD', margin=0.0010, shape_method='CONVEX', merge_overlap=False, pin=True)
                        bpy.ops.uv.pin(clear=False)

                        for face in bm.faces:
                            if face.index in originally_hidden_faces:
                                face.hide_set(True)

                        bmesh.update_edit_mesh(mesh)
                        restore()
                                                                    
                except Exception as e:
                    print("No active face selection")
                    print(f"An error occurred: {e}")
                    pass
            else:
                return {'FINISHED'} 

        def inpaint_extend_new(extend_size=10, flush=False):

            scene = bpy.context.scene      
            scene.compositing_node_group = bpy.data.node_groups.new("UVDissectionCompositor", 'CompositorNodeTree')            
            node_tree = scene.compositing_node_group
            node_tree.nodes.clear()
            
            # Create nodes
            image_node = node_tree.nodes.new("CompositorNodeRLayers")
            
            inpaint_node = node_tree.nodes.new('CompositorNodeInpaint')
            inpaint_node.inputs[1].default_value = extend_size
            
            viewer_node = node_tree.nodes.new('NodeGroupOutput')
            node_tree.interface.new_socket("Image", socket_type="NodeSocketColor", in_out='OUTPUT')
            
            # Connect nodes
            if flush:
                set_alpha_node = node_tree.nodes.new('CompositorNodeSetAlpha') 
                set_alpha_node.inputs[2].default_value = 'Replace Alpha'
                node_tree.links.new(image_node.outputs['Image'], inpaint_node.inputs['Image'])
                node_tree.links.new(inpaint_node.outputs['Image'], set_alpha_node.inputs['Image'])
                node_tree.links.new(set_alpha_node.outputs['Image'], viewer_node.inputs['Image'])
                               
            else:
                node_tree.links.new(image_node.outputs['Image'], inpaint_node.inputs['Image'])
                node_tree.links.new(inpaint_node.outputs['Image'], viewer_node.inputs['Image'])

            return node_tree 
                                
        def add_nodes(node_group, changed_uv):

            splitedge_node = node_group.nodes.new('GeometryNodeSplitEdges')
            setpos_node = node_group.nodes.new('GeometryNodeSetPosition')
            named_node = node_group.nodes.new('GeometryNodeInputNamedAttribute')
            named_node.inputs[0].default_value = changed_uv
            named_node.data_type = "FLOAT_VECTOR"

            input_node = node_group.nodes.get('Group Input')
            output_node = node_group.nodes.get('Group Output')

            node_group.links.new(input_node.outputs['Geometry'], splitedge_node.inputs['Mesh'])
            node_group.links.new(splitedge_node.outputs['Mesh'], setpos_node.inputs['Geometry'])
            node_group.links.new(named_node.outputs['Attribute'], setpos_node.inputs['Position'])
            node_group.links.new(output_node.inputs['Geometry'], setpos_node.outputs['Geometry'])

            return node_group  

        def transfer_uv(objects, source, target):
            for obj in objects:
                if obj.type == 'MESH':
                    source_uv = obj.data.uv_layers.get(source)
                    target_uv = obj.data.uv_layers.get(target)
                    if source_uv and target_uv:
                        for loop in obj.data.loops:
                            target_uv.data[loop.index].uv = source_uv.data[loop.index].uv    

        def manage_settings(settings_dict, restore=False):
            scene = bpy.context.scene            
            for path, (original_val, new_val) in settings_dict.items():
                if restore:
                    # RESTORE: Use original value
                    value_to_set = original_val
                    action = "Restored"
                else:
                    # APPLY: Use new value, skip if "skip"
                    if new_val == "skip":
                        continue
                    value_to_set = new_val
                    action = "Applied"
                
                # Split path and navigate
                parts = path.split('.')
                obj = scene
                
                # Navigate to parent object
                for attr in parts[:-1]:
                    obj = getattr(obj, attr)
                
                # Set the value
                setattr(obj, parts[-1], value_to_set)
                print(f"{action} {path} = {value_to_set}")

        if self.mode == 2:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            for obj in matching_objects:
                if obj.type == "MESH":
                    for uv_map in obj.data.uv_layers:
                        if "_temp" in uv_map.name:
                            obj.data.uv_layers.remove(uv_map)
                        if uv_map.name == "UVDC_UVMap":
                            obj.data.uv_layers.active = uv_map  
                    if obj == original_selected:
                        obj.select_set(True)
            self.report({'INFO'}, "Cancelled!") 
            
            uvdc_props.record_mode = True
            bpy.ops.object.mode_set(mode=uvdc_props.object_mode)
            return {'FINISHED'}

        bpy.ops.object.mode_set(mode='OBJECT')

        original_interpolations = {}
        # Get the active object
        obj = context.active_object          
        name = "UVDissectionCompositor"
        object_locations = {}
        for object in matching_objects:
            if object.type == "MESH":
                for material in object.data.materials:
                    if material.use_nodes:
                        node_tree = material.node_tree
                        for node in node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                if node.image.name in image_list:
                                    original_interpolations[node] = node.interpolation
                                    node.interpolation = "Closest"

                object.data.uv_layers.active =  object.data.uv_layers.get("UVDC_UVMap")
                object_locations[object.name] = object.location.copy()
                object.location[0] = 0
                object.location[1] = 0
                object.location[2] = 0

                try:
                    modifier = object.modifiers.get(name)
                except:
                    pass
                if modifier is None:
                    modifier = object.modifiers.new(name, 'NODES')
                    try:
                        modifier.node_group = bpy.data.node_groups[name+"GeometryGroup"]
                    except:
                        pass
                    if modifier.node_group is None:
                        bpy.ops.node.new_geometry_node_group_assign()        
                        modifier.node_group.name = name+"GeometryGroup"
                        if self.mode == 3 or self.mode == 5:
                            put_nodes = add_nodes(modifier.node_group, object.data.uv_layers.active.name)
                        else:
                            put_nodes = add_nodes(modifier.node_group, "UVDC_UVMap_temp")

        camera_data = bpy.data.cameras.new(name="Camera")
        newcam = bpy.data.objects.new("Camera", camera_data)
        bpy.context.collection.objects.link(newcam)
        newcam.name = "UVDissectionCamera"
        context.scene.camera = newcam

        newcam.location[0] = 0
        newcam.location[1] = 0
        newcam.location[2] = 100

        newcam.rotation_euler[0] = 0
        newcam.rotation_euler[1] = 0
        newcam.rotation_euler[2] = 0

        newcam.data.name = 'newcam'
        newcam.data.type = 'ORTHO'
        newcam.data.ortho_scale = 1
        newcam.data.shift_x = 0.5
        newcam.data.shift_y = 0.5

        # Store original settings        

        settings_dict = {
            #display_settings:
            'display.shading.light': [scene.display.shading.light, "FLAT"],
            'display.shading.color_type': [scene.display.shading.color_type, 'TEXTURE'],
            'display.render_aa': [scene.display.render_aa, 'OFF'],
            #render_settings:
            'render.engine': [scene.render.engine, 'BLENDER_WORKBENCH'],
            'render.film_transparent': [scene.render.film_transparent, True],
            'render.dither_intensity': [scene.render.dither_intensity, 0],            
            'render.resolution_x': [scene.render.resolution_x, "skip"],
            'render.resolution_y': [scene.render.resolution_y, "skip"],
            'eevee.taa_render_samples': [scene.eevee.taa_render_samples, 1],
            #image_settings: 
            'render.filepath': [scene.render.filepath, "skip"],            
            'render.image_settings.file_format': [scene.render.image_settings.file_format, 'PNG'],
            'render.image_settings.color_mode': [scene.render.image_settings.color_mode, 'RGBA'],
            'render.image_settings.compression': [scene.render.image_settings.compression, 0],
            'render.image_settings.color_depth': [scene.render.image_settings.color_depth, '8'],
        
        }
        original_settings_dict = settings_dict.copy()
        manage_settings(settings_dict, restore=False)

        if self.mode == 3 or self.mode == 5:
            scene.render.engine = 'BLENDER_EEVEE'

        if uvdc_props.do_extend:
            compositor_nodes = inpaint_extend_new(uvdc_props.margin, flush=True)

        new_images = []
        for image in image_list:
            if self.mode == 3 or self.mode == 5:
                if image != bpy.data.images.get(uvdc_props.uvdc_renderchain_menu_node_image):
                    continue
            for object in matching_objects:
                if object.type == "MESH":
                    for uv_map in obj.data.uv_layers:
                        if uv_map.name == 'UVDC_UVMap':
                            obj.data.uv_layers.active = uv_map
                            break
                    materials_tracked = []
                    for material in object.data.materials:
                        materials_tracked.append(material)
                        if material in materials_tracked and material.use_nodes:
                            node_tree = material.node_tree
                            for node in node_tree.nodes:

                                if node.type == 'TEX_IMAGE' and node.image and node.image.name == image.name:
                                    material.node_tree.nodes.active = node

                                if self.mode == 5:
                                    if node.type == 'MENU_SWITCH' and (node.name == uvdc_props.uvdc_renderchain_menu_node_name or node.label == uvdc_props.uvdc_renderchain_menu_node_name):
                                        node.inputs[0].default_value = uvdc_props.uvdc_renderchain_menu_node_input
          
            scene.render.resolution_x = image.size[0]
            scene.render.resolution_y = image.size[1]

            #return {'FINISHED'}


            render_path = os.path.join(bpy.app.tempdir, image.name + "_uvdc_temp.png")
            bpy.context.scene.render.filepath = render_path
            bpy.ops.render.render(write_still=True)
        
            new_image = bpy.data.images.load(render_path)
            new_image.alpha_mode = 'CHANNEL_PACKED'
            image_name = image.name
            image.name = image.name + "_remove"
            new_image.name = image_name
            new_images.append(new_image)

        for image in image_list:  
            if self.mode == 3 or self.mode == 5:
                if image != bpy.data.images.get(uvdc_props.uvdc_renderchain_menu_node_image + "_remove"):
                    continue             
            for object in matching_objects:
                
                if object.type == "MESH":
                    materials_tracked = []
                    for material in object.data.materials:
                        materials_tracked.append(material)
                        if material in materials_tracked and material.use_nodes:
                            node_tree = material.node_tree
                            for node in node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and node.image and node.image.name == image.name:
                                    node.image = new_images.pop(0)
                                if self.mode == 5:
                                    if node.type == 'MENU_SWITCH' and (node.name == uvdc_props.uvdc_renderchain_menu_node_name or node.label == uvdc_props.uvdc_renderchain_menu_node_name):
                                        node.inputs[0].default_value = uvdc_props.uvdc_renderchain_menu_node_restore

            bpy.data.images.remove(image)
        try:    
            render = bpy.data.images.get("Render Result")
            bpy.data.images.remove(render)
        except:
            pass

        img = bpy.data.images.get(original_canvas)
        if img:
            context.scene.tool_settings.image_paint.canvas = img
            for area in bpy.context.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    area.spaces.active.image = img
                    break

        if uvdc_props.do_extend:
            bpy.data.node_groups.remove(compositor_nodes)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in matching_objects:
            if obj.type == "MESH":
                for node, original_interpolation in original_interpolations.items():
                    node.interpolation = original_interpolation

                obj.modifiers.remove(obj.modifiers[-1])
                for uv_map in obj.data.uv_layers:
                    transfer_uv(matching_objects, "UVDC_UVMap_temp", "UVDC_UVMap")
                    if "_temp" in uv_map.name:
                        obj.data.uv_layers.remove(uv_map)
                    if uv_map.name == "UVDC_UVMap":
                        obj.data.uv_layers.active = uv_map
            if obj == original_selected:
                obj.select_set(True)

        bpy.data.node_groups.remove(put_nodes)
        for obj_name, location in object_locations.items():
            obj = bpy.data.objects.get(obj_name)
            if obj:
                obj.location = location

        for obj in og_hidden:
            if obj.hide_get() is False:
                obj.hide_set(True)

        camera_data = newcam.data
        bpy.data.objects.remove(newcam)
        bpy.data.cameras.remove(camera_data)

        manage_settings(original_settings_dict, restore=True)

        bpy.ops.object.mode_set(mode=uvdc_props.object_mode)
        bpy.ops.file.pack_all()
        try:
            bpy.ops.image.save_all_modified()
        except:
            pass
        self.report({'INFO'}, "Bake complete!") 

        uvdc_props.record_mode = True
        return {'FINISHED'} 

class UVDC_OT_select_this_canvas(bpy.types.Operator):
    bl_idname = "uvdc.select_this_canvas"
    bl_label = "Set as Paint Canvas"
    
    image_name: bpy.props.StringProperty()
    
    def execute(self, context):
        img = bpy.data.images.get(self.image_name)
        if img:
            bpy.ops.object.mode_set(mode="TEXTURE_PAINT")
            context.scene.tool_settings.image_paint.canvas = img
            context.scene.tool_settings.image_paint.mode = 'IMAGE'
            for area in bpy.context.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    area.spaces.active.image = img
                    break
        return {'FINISHED'}   

class UVDC_OT_set_as_hidden(bpy.types.Operator):
    bl_idname = "uvdc.set_as_hidden"
    bl_label = "Set as hidden"
    
    image_name: bpy.props.StringProperty()
    
    def execute(self, context):
        img = bpy.data.images.get(self.image_name)
        if img:
            if img.get('enable', True):
                img['enable'] = False 
            else:
                img['enable'] = True

        return {'FINISHED'}   

class UV_PT_UVDC(bpy.types.Panel):
    bl_idname = "UV_PT_UVDC"
    bl_label = "UV Dissection Compositor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'UVDC'

    def draw(self, context):
        layout = self.layout
        uvdc_props = context.scene.uvdc_properties
        _, users, images = get_images_and_users(context.object)



        box4 = layout.box()
        row = box4.row()
        if not uvdc_props.autounwrap:
            if uvdc_props.record_mode:
                row.operator("wm.uvdissectioncompositor", text="Change UV", icon="UV").mode = 1
            else:
                row.alert = True
                row.operator("wm.uvdissectioncompositor", text="Apply", icon="GROUP_UVS").mode = 0
                row.operator("wm.uvdissectioncompositor", text="", icon="PANEL_CLOSE").mode = 2
                box = layout.box()
        else:
            row.operator("wm.uvdissectioncompositor", text="AutoUnwrap", icon="MOD_UVPROJECT").mode = 4

        if not uvdc_props.uvdc_renderchain_menu_node_enable:
            box = layout.box()
            row = box.row()
            row.operator("wm.uvdissectioncompositor", text="EEVEE Snapshot", icon="RESTRICT_RENDER_OFF").mode = 3

            row = box.row()
            row.label(text='Image:')
            row.prop(uvdc_props, "uvdc_renderchain_menu_node_image", text= "")  
            row = box.row()
            box = row.box()
            row = box.row()
            row.prop(uvdc_props, "uvdc_renderchain_menu_node_enable", text= "Use Separate Output")                    

        else:
            box = layout.box()
            row = box.row()
            row.operator("wm.uvdissectioncompositor", text="*EEVEE Snapshot*", icon="RESTRICT_RENDER_OFF").mode = 5
            row = box.row()     
            row.label(text='Image:')
            row.prop(uvdc_props, "uvdc_renderchain_menu_node_image", text= "")      
            row = box.row()
            box = row.box()
            row = box.row()
            row.prop(uvdc_props, "uvdc_renderchain_menu_node_enable", text= "Use Separate Output")                             
            row = box.row()
            if uvdc_props.coll_listg == False: 
                row.prop(uvdc_props, "coll_listg", text= f"Menu Switch Node", icon='DOWNARROW_HLT', toggle=False, emboss=False)

                row = box.row()
                row.label(text='Name\Label:')
                row.prop(uvdc_props, "uvdc_renderchain_menu_node_name", text= "")   
                row = box.row()
                row.label(text='Switch to:')
                row.prop(uvdc_props, "uvdc_renderchain_menu_node_input", text= "") 
                row = box.row()
                row.label(text='Switch back:')
                row.prop(uvdc_props, "uvdc_renderchain_menu_node_restore", text= "")            
            else: 
                row.prop(uvdc_props, "coll_listg", text= f"Menu Switch Node", icon='RIGHTARROW', toggle=False, emboss=False)


        row = box4.row()
        split = row.split(factor=0.7)
        row = split.row()
        row.prop(uvdc_props, "do_extend", text= "Extend pixels")
        if uvdc_props.do_extend:
            row = split.row()
            row.prop(uvdc_props, "margin", text= "")
            row.active = True
        else:
            row = split.row()
            row.prop(uvdc_props, "margin", text= "")
            row.active = False

        row = box4.row()
        split = row.split(factor=0.7)
        row = split.row()
        row.prop(uvdc_props, "autounwrap", text= "Auto Unwrap")
        if uvdc_props.autounwrap:
            row = split.row()
            row.prop(uvdc_props, "uv_scale_multiplier", text= "")
            row.active = True
        else:
            row = split.row()
            row.prop(uvdc_props, "uv_scale_multiplier", text= "")
            row.active = False

        box = layout.box()
        row = box.row()
        try:
            if uvdc_props.coll_list == False:                
                row.prop(uvdc_props, "coll_list", text= f"Linked Objects: ({len(users)})", icon='RIGHTARROW', toggle=False, emboss=False)
            else:
                row.prop(uvdc_props, "coll_list", text= "Linked Objects:", icon='DOWNARROW_HLT', toggle=False, emboss=False)    
                for obj in users:
                    if obj.type == 'MESH':
                        row2 = box.row()
                        row2.label(text=obj.name)

        except:
            pass
        
        # 2. Show current canvas
        ip = context.scene.tool_settings.image_paint
        current = ip.canvas if hasattr(ip, 'canvas') else None

        box_k = layout.box()
        box2 = box_k.box()
        # 3. Show images as buttons with clear buttons
        if len(images) != 0:
            
            row = box2.row()
            row.label(text="Image Nodes:", icon="NODE")
            
            # Get the cloak image name from properties
                      
            for img in images:
                row = box2.row()
                # Split row into two parts: select button and clear button
                split = row.split(factor=0.85)  # 80% for select, 20% for clear
                
                # Left side: Select button
                left_row = split.row()
                if img == current and context.scene.tool_settings.image_paint.mode == 'IMAGE' and context.object.mode == 'TEXTURE_PAINT':
                    left_row.alert = True
                    left_row.operator("uvdc.select_this_canvas", 
                                text=img.name, 
                                
                                emboss=False).image_name = img.name
                else:
                    left_row.operator("uvdc.select_this_canvas", 
                                    text=img.name, 
                                    ).image_name = img.name
                
                # Right side: Clear button (only if this is the cloak image)
                right_row = split.row()
                # Empty space for alignment
                if img.get('enable', True) or 'enable' not in img:
                    right_row.operator("uvdc.set_as_hidden", 
                                        text="", icon="CHECKBOX_HLT" 
                                        ).image_name = img.name
                    right_row.active = True
                else:  
                    right_row.operator("uvdc.set_as_hidden", 
                                        text="", icon="CHECKBOX_DEHLT" 
                                        ).image_name = img.name
                    right_row.active = False                                    
        else:
            box2.label(text="No images in material", icon='INFO')
   


classes = (
    UVDC_Properties,
    UVDC_Properties_List,
    UV_Dissection_Compositor,
    UV_PT_UVDC,
    UVDC_OT_select_this_canvas,
    UVDC_OT_set_as_hidden
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uvdc_properties = bpy.props.PointerProperty(type=UVDC_Properties)
    bpy.types.Scene.uvdc_list = bpy.props.CollectionProperty(type=UVDC_Properties_List)
    bpy.types.Scene.uvdc_list_active_index = bpy.props.IntProperty()
    bpy.types.Scene.uvdc_collection = bpy.props.PointerProperty(
        name="Objects to dissect",
        type=bpy.types.Collection
    )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.uvdc_properties
    del bpy.types.Scene.uvdc_list
    del bpy.types.Scene.uvdc_list_active_index
    del bpy.types.Scene.uvdc_collection
if __name__ == "__main__":
    register()              