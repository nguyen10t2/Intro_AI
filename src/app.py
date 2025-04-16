from tkintermapview import TkinterMapView
import customtkinter
from graph import Graph
from algorithm import *
import time
import osmnx as ox
from functools import lru_cache
import threading


class App(customtkinter.CTk):
    APP_NAME = "Map View - Kim Mã, Ba Đình"
    # CENTER_LAT, CENTER_LON = 21.0331439, 105.8234067
    CENTER_LAT, CENTER_LON = 21.0329236, 105.8226289
    source_path = r"res/map.osm"
    ALGORITHMS = {
        "A*": lambda self: AStar(self.distance),
        "Dijkstra": lambda _: Dijkstra(),
        "Greedy": lambda self: Greedy(self.distance),
        "BFS": lambda _: BFS(),
        "DFS": lambda _: DFS(),
        "Bellman-Ford": lambda _: BellmanFord(),
        "Bidirectional A*": lambda self: BidirectionalAStar(self.distance)
    }
    
    def __init__(self):
        super().__init__()
        self.title(self.APP_NAME)
        self.geometry("1000x700")
        self.resizable(True, True)  # Cho phép điều chỉnh kích thước cửa sổ

        # Khởi tạo biến instance
        self.graph = Graph()
        self.start_node = None
        self.goal_node = None
        self.markers = []
        self.path_line = None
        self.loading_indicator = None
        self.g = None  # Sẽ được tải trong phương thức load_graph

        # Thiết lập giao diện và bản đồ
        self._setup_ui()
        self._initialize_map()
        
        # Đăng ký sự kiện đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Tải dữ liệu bản đồ trong một luồng riêng biệt
        self.load_map_thread = threading.Thread(target=self.load_graph)
        self.load_map_thread.daemon = True
        self.load_map_thread.start()

    def _setup_ui(self):
        # Tạo layout chính
        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Bản đồ
        self.map_frame = customtkinter.CTkFrame(self, corner_radius=0)
        self.map_frame.grid(row=0, column=0, sticky="nsew")
        self.map_frame.grid_rowconfigure(0, weight=1)
        self.map_frame.grid_columnconfigure(0, weight=1)
        
        self.map_widget = TkinterMapView(self.map_frame, corner_radius=0)
        self.map_widget.grid(row=0, column=0, sticky="nsew")

        # Control Panel
        self.panel = customtkinter.CTkFrame(self)
        self.panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Thiết lập các widget trong panel
        padding = 10
        
        self.title_label = customtkinter.CTkLabel(
            self.panel, 
            text="Tìm đường đi",
            font=customtkinter.CTkFont(size=18, weight="bold")
        )
        self.title_label.pack(pady=(20, padding))
        
        self.instruction_label = customtkinter.CTkLabel(
            self.panel,
            text="Chọn 2 điểm trên bản đồ\nđể thiết lập điểm đầu và điểm đích",
            font=customtkinter.CTkFont(size=12),
            justify="center"
        )
        self.instruction_label.pack(pady=padding)
        
        self.status_label = customtkinter.CTkLabel(
            self.panel,
            text="Đang tải bản đồ...",
            font=customtkinter.CTkFont(size=12),
            text_color="orange"
        )
        self.status_label.pack(pady=padding)

        self.alg_label = customtkinter.CTkLabel(self.panel, text="Thuật toán:")
        self.alg_label.pack(pady=(20, 5))

        self.alg_selector = customtkinter.CTkComboBox(
            self.panel, values=list(self.ALGORITHMS.keys())
        )
        self.alg_selector.pack(pady=padding)

        self.run_button = customtkinter.CTkButton(
            self.panel, 
            text="Tìm đường", 
            command=self.run_algorithm_thread,
            state="disabled"
        )
        self.run_button.pack(pady=padding*2)

        self.clear_button = customtkinter.CTkButton(
            self.panel, 
            text="Xoá chọn", 
            command=self.clear_selection,
            fg_color="#D35B58", 
            hover_color="#C77C78"
        )
        self.clear_button.pack(pady=padding)
        
        # Thêm widget hiển thị thông tin về đường đi
        self.info_frame = customtkinter.CTkFrame(self.panel)
        self.info_frame.pack(pady=padding, fill="x", padx=padding)
        
        self.distance_label = customtkinter.CTkLabel(
            self.info_frame,
            text="Khoảng cách: N/A",
            anchor="w"
        )
        self.distance_label.pack(pady=5, anchor="w")
        
        self.nodes_label = customtkinter.CTkLabel(
            self.info_frame,
            text="Số nút đã duyệt: N/A",
            anchor="w"
        )
        self.nodes_label.pack(pady=5, anchor="w")

        self.time_label = customtkinter.CTkLabel(
            self.info_frame,
            text="Thời gian tìm kiếm: N/A",
            anchor="w"
        )
        self.time_label.pack(pady=5, anchor="w")
        

    def _initialize_map(self):
        self.map_widget.set_position(self.CENTER_LAT, self.CENTER_LON)
        self.map_widget.set_zoom(17)
        self.map_widget.add_right_click_menu_command("Đặt điểm đầu", self.set_start_marker)
        self.map_widget.add_right_click_menu_command("Đặt điểm đích", self.set_goal_marker)
        
        # Giữ nguyên sự kiện chuột để điều hướng bản đồ
        self.map_widget.canvas.bind("<Button-1>", self.on_map_click)

        # Tắt hoàn toàn sự kiện chuột mặc định của bản đồ
        for event in ("<B1-Motion>", "<ButtonRelease-1>"):
            self.map_widget.canvas.unbind(event)

    def on_map_click(self, event):
        # Nếu đã có cả điểm đầu và điểm đích, không cho phép thêm điểm mới
        if self.start_node and self.goal_node:
            return None
        
        lat, lon = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        
        if not self.g:
            return  # Bản đồ chưa được tải xong
            
        print(f"Clicked at: {lat}, {lon}")
        node = self.find_nearest_node(lat, lon)
        print(f"Nearest node: {node}")
        
        marker = self.map_widget.set_marker(lat, lon)
        self.markers.append(marker)

        if not self.start_node:
            self.start_node = node
            marker.set_text("Điểm đầu")
            # Đặt màu cho marker thay vì sử dụng icon
            if hasattr(marker, "canvas_id"):
                self.map_widget.canvas.itemconfig(marker.canvas_id, fill="green")
        elif not self.goal_node:
            self.goal_node = node
            marker.set_text("Điểm đích")
            # Đặt màu cho marker thay vì sử dụng icon
            if hasattr(marker, "canvas_id"):
                self.map_widget.canvas.itemconfig(marker.canvas_id, fill="red")
            
        self.update_run_button()
    
    def set_start_marker(self, coords):
        if self.start_node:
            # Xóa marker cũ nếu đã có
            for marker in self.markers:
                if hasattr(marker, "text") and marker.text == "Điểm đầu":
                    self.markers.remove(marker)
                    marker.delete()
        
        lat, lon = coords
        if not self.g:
            return  # Bản đồ chưa được tải xong
            
        node = self.find_nearest_node(lat, lon)
        
        marker = self.map_widget.set_marker(lat, lon, text="Điểm đầu")
        # Đặt màu cho marker thay vì sử dụng icon
        if hasattr(marker, "canvas_id"):
            self.map_widget.canvas.itemconfig(marker.canvas_id, fill="green")
        self.markers.append(marker)
        self.start_node = node
        
        self.update_run_button()
    
    def set_goal_marker(self, coords):
        if self.goal_node:
            # Xóa marker cũ nếu đã có
            for marker in self.markers:
                if hasattr(marker, "text") and marker.text == "Điểm đích":
                    self.markers.remove(marker)
                    marker.delete()
        
        lat, lon = coords
        if not self.g:
            return  # Bản đồ chưa được tải xong
            
        node = self.find_nearest_node(lat, lon)
        
        marker = self.map_widget.set_marker(lat, lon, text="Điểm đích")
        # Đặt màu cho marker thay vì sử dụng icon
        if hasattr(marker, "canvas_id"):
            self.map_widget.canvas.itemconfig(marker.canvas_id, fill="red")
        self.markers.append(marker)
        self.goal_node = node
        
        self.update_run_button()
    
    def set_marker_color(self, marker, color):
        """Thiết lập màu cho marker nếu có thể"""
        if hasattr(marker, "canvas_id"):
            self.map_widget.canvas.itemconfig(marker.canvas_id, fill=color)
    
    def update_run_button(self):
        if self.start_node and self.goal_node and self.g:
            self.run_button.configure(state="normal")
        else:
            self.run_button.configure(state="disabled")

    def load_graph(self):
        try:
            # Tải dữ liệu đồ thị từ file OSM
            self.g = ox.graph_from_xml(self.source_path, retain_all=True, simplify=False)
            
            # Chuyển đổi sang đồ thị nội bộ
            for node_id, data in self.g.nodes(data=True):
                self.graph.add_node(node_id, data['y'], data['x'])
            
            for u, v, data in self.g.edges(data=True):
                self.graph.add_edge(u, v, data['length'])
            
            # Cập nhật giao diện sau khi tải xong
            self.after(0, self.on_graph_loaded)
        except Exception as e:
            # Xử lý lỗi và thông báo cho người dùng
            print(f"Lỗi khi tải bản đồ: {e}")
            self.after(0, lambda: self.status_label.configure(
                text=f"Lỗi tải bản đồ: {str(e)[:50]}...", 
                text_color="red"
            ))
    
    def on_graph_loaded(self):
        self.status_label.configure(text="Bản đồ đã sẵn sàng", text_color="green")
        self.update_run_button()
    
    @lru_cache(maxsize=128)
    def find_nearest_node(self, lat, lon):
        """Tìm nút gần nhất với tọa độ đã cho, với cache để tăng hiệu suất"""
        return self.graph.find_nearest_node_within_radius(lat, lon, initial_radius=10, step=10, max_radius=1000)

    def run_algorithm_thread(self):
        """Khởi chạy thuật toán trong một luồng riêng biệt"""
        if not self.start_node or not self.goal_node:
            return
            
        # Hiển thị trạng thái đang tìm đường
        self.status_label.configure(text="Đang tìm đường...", text_color="orange")
        self.run_button.configure(state="disabled")
        
        # Khởi chạy thuật toán trong một luồng riêng
        thread = threading.Thread(target=self.run_algorithm)
        thread.daemon = True
        thread.start()

    def run_algorithm(self):
        try:
            algo_name = self.alg_selector.get()
            algorithm_creator = self.ALGORITHMS.get(algo_name)
            if not algorithm_creator:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Không tìm thấy thuật toán: {algo_name}", 
                    text_color="red"
                ))
                return
                
            algo = algorithm_creator(self)
            # Cần điều chỉnh hàm run() trong các lớp thuật toán để trả về cả path và stats
            # Nhưng hiện tại lớp thuật toán có thể chỉ trả về path, nên chúng ta cần xử lý cả hai trường hợp
            time_start = time.time()
            result = algo.run(self.start_node, self.goal_node, self.graph)
            time_total = (time.time() - time_start) * 1000
            
            # Kiểm tra kết quả trả về
            if isinstance(result, tuple) and len(result) == 2:
                count_nodes, path = result
                stats = {"distance": self.calculate_path_distance(path) if path else 0, "expanded_nodes": count_nodes, "time": time_total}
            else:
                path = result
                stats = {"distance": self.calculate_path_distance(path) if path else 0, "expanded_nodes": "N/A", "time": time_total}
            
            if path:
                # Cập nhật UI trên luồng chính
                self.after(0, lambda: self.draw_path(path, stats))
                self.after(0, lambda: self.status_label.configure(
                    text=f"Đã tìm thấy đường đi ({algo_name})", 
                    text_color="green"
                ))
            else:
                self.after(0, lambda: self.status_label.configure(
                    text="Không tìm thấy đường đi", 
                    text_color="red"
                ))
        except Exception as e:
            
            error_message = f"Lỗi: {str(e)[:50]}..."
            print(error_message)
            self.after(2000, lambda lbl=self.status_label, msg=error_message: lbl.configure(text=msg))
        
        # Kích hoạt lại nút tìm đường
        self.after(0, lambda: self.run_button.configure(state="normal"))

    def clear_selection(self):
        for marker in self.markers:
            marker.delete()
        self.markers.clear()
        self.start_node = None
        self.goal_node = None
        self.map_widget.delete_all_path()
        # Đặt lại nhãn thông tin
        self.distance_label.configure(text="Khoảng cách: N/A")
        self.nodes_label.configure(text="Số nút đã duyệt: N/A")
        self.time_label.configure(text="Thời gian tìm kiếm: N/A")
        self.status_label.configure(text="Bản đồ đã sẵn sàng", text_color="green")
        
        # Cập nhật trạng thái nút tìm đường
        self.update_run_button()

    @lru_cache(maxsize=1024)
    def distance(self, u, v):
        """Tính khoảng cách giữa hai nút, với cache để tăng hiệu suất"""
        return self.graph.heuristic(u, v)  # Sử dụng hàm heuristic của đồ thị
        
    def calculate_path_distance(self, path):
        """Tính tổng khoảng cách của đường đi"""
        if not path or len(path) < 2:
            return 0
            
        total_distance = 0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # Sử dụng độ dài cạnh từ dữ liệu gốc nếu có
            if self.graph.has_edge(u, v):
                total_distance += self.graph.cost(u, v)
            else:
                total_distance += self.distance(u, v) * 111000  # Chuyển từ độ sang mét (xấp xỉ)
                
        return total_distance

    def on_closing(self, event=None):
        # Đảm bảo các luồng con dừng lại khi đóng ứng dụng
        self.quit()
        self.destroy()

    def draw_path(self, path, stats=None):
        if not path:
            return
            
        # Vẽ đường đi trên bản đồ
        coords = [self.graph.nodes[n] for n in path]
        self.map_widget.delete_all_path()
        self.path_line = self.map_widget.set_path(coords, color="blue", width=5)
        
        # Cập nhật thông tin về đường đi
        if stats:
            self.distance_label.configure(text=f"Khoảng cách: {stats.get('distance', 'N/A'):.2f} m")
            self.nodes_label.configure(text=f"Số nút đã duyệt: {stats.get('expanded_nodes', 'N/A')}")
            self.time_label.configure(text=f"Thời gian tìm kiếm: {stats.get('time', 'N/A'):.3f} ms")


if __name__ == '__main__':
    customtkinter.set_appearance_mode("System")  # Hỗ trợ chế độ giao diện hệ thống
    customtkinter.set_default_color_theme("blue")  # Đặt chủ đề màu sắc
    
    app = App()
    app.mainloop()