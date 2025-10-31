"""
OpenGL渲染管理器 - 终极完整增强版 v8.5.4
===============================================================
新增功能：
1. LRU算法的纹理智能清理与管理
2. 纹理内存使用监控
3. 智能缓存淘汰策略
4. 内存压力自适应清理

修复内容：
1. 字体渲染颠倒问题 - 修复纹理坐标
2. 完整功能演示 - 包含所有系统功能展示
3. 自定义字体支持 - 创建文本时可指定字体和字号
4. 中文支持优化 - 修复汉字显示为方块的问题
5. 文本缓存优化 - 大幅提升性能
"""

import pygame
import time
import math
import os
import random
import numpy as np
from typing import Dict, List, Tuple, Optional, Callable, Any, Union
from collections import OrderedDict
from OpenGL.GL import *
from OpenGL.GLU import *

class LRUTextureCache:
    """LRU纹理缓存管理器"""
    
    def __init__(self, max_size_mb=100, cleanup_threshold=0.8):
        """
        初始化LRU纹理缓存
        
        Args:
            max_size_mb: 最大缓存大小(MB)
            cleanup_threshold: 清理阈值(0-1)，当内存使用超过该比例时触发清理
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cleanup_threshold = cleanup_threshold
        self.cache = OrderedDict()  # 保持访问顺序
        self.total_memory_usage = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        
    def put(self, key, texture_data):
        """添加纹理到缓存"""
        texture_size = self._calculate_texture_size(texture_data)
        
        # 如果纹理太大，直接不缓存
        if texture_size > self.max_size_bytes * 0.1:  # 单个纹理不超过总缓存的10%
            return False
            
        # 如果缓存已满，先清理空间
        if self.total_memory_usage + texture_size > self.max_size_bytes * self.cleanup_threshold:
            self._cleanup(self.max_size_bytes * 0.5)  # 清理到50%使用率
            
        # 如果键已存在，先移除旧数据
        if key in self.cache:
            old_data = self.cache[key]
            self.total_memory_usage -= self._calculate_texture_size(old_data)
            del self.cache[key]
        
        # 添加新数据
        self.cache[key] = texture_data
        self.total_memory_usage += texture_size
        
        # 移动到最近使用位置
        self.cache.move_to_end(key)
        return True
        
    def get(self, key):
        """从缓存获取纹理"""
        if key in self.cache:
            # 移动到最近使用位置
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        else:
            self.misses += 1
            return None
            
    def contains(self, key):
        """检查缓存是否包含指定键"""
        return key in self.cache
        
    def remove(self, key):
        """从缓存移除纹理"""
        if key in self.cache:
            texture_data = self.cache[key]
            texture_size = self._calculate_texture_size(texture_data)
            self.total_memory_usage -= texture_size
            del self.cache[key]
            return True
        return False
        
    def _cleanup(self, target_size):
        """清理缓存到目标大小"""
        if self.total_memory_usage <= target_size:
            return
            
        keys_to_remove = []
        current_size = self.total_memory_usage
        
        # 从最久未使用的开始清理
        for key, texture_data in self.cache.items():
            if current_size <= target_size:
                break
                
            texture_size = self._calculate_texture_size(texture_data)
            current_size -= texture_size
            keys_to_remove.append(key)
            self.evictions += 1
            
        # 执行清理
        for key in keys_to_remove:
            texture_data = self.cache[key]
            # 释放OpenGL纹理
            if 'texture_id' in texture_data:
                try:
                    glDeleteTextures([texture_data['texture_id']])
                except:
                    pass
            del self.cache[key]
            
        self.total_memory_usage = current_size
        
    def _calculate_texture_size(self, texture_data):
        """计算纹理内存大小"""
        if 'width' in texture_data and 'height' in texture_data:
            # 估算RGBA纹理大小 (4 bytes per pixel)
            return texture_data['width'] * texture_data['height'] * 4
        return 0
        
    def get_stats(self):
        """获取缓存统计信息"""
        hit_rate = self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        return {
            'total_size_mb': self.total_memory_usage / (1024 * 1024),
            'max_size_mb': self.max_size_bytes / (1024 * 1024),
            'texture_count': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': hit_rate
        }
        
    def clear(self):
        """清空缓存"""
        for texture_data in self.cache.values():
            if 'texture_id' in texture_data:
                try:
                    glDeleteTextures([texture_data['texture_id']])
                except:
                    pass
        self.cache.clear()
        self.total_memory_usage = 0

class OpenGLRenderManager:
    """
    OpenGL渲染管理器 - 终极完整增强版 v8.5.4
    新增LRU纹理智能管理，修复字体渲染问题，提供完整功能演示
    """
    
    def __init__(
        self,
        window_size: Tuple[int, int] = (960, 540),
        window_title: str = "OpenGL渲染管理器 v8.5.4",
        target_fps: int = 60,
        manual_fps_control: bool = False,
        enable_performance_stats: bool = True,
        enable_audio: bool = True,
        audio_channels: int = 16,
        window_icon: str = None,
        coordinate_origin: str = 'top_left',
        reference_point: str = 'top_left',
        global_scaling_mode: str = 'none',
        global_scale_factor: float = 1.0,
        font_config: Dict = None,
        enable_physics: bool = True,
        enable_particles: bool = True,
        performance_theme: Dict = None,
        texture_cache_size_mb: int = 100,  # 新增：纹理缓存大小配置
        **window_flags
    ):
        """初始化渲染管理器"""
        # 初始化状态标志
        self._initialized = False
        self._cleaned_up = False
        
        # 存储配置参数
        self.original_window_size = window_size
        self.window_size = window_size
        self.window_title = window_title
        self.original_window_title = window_title
        self.target_fps = target_fps
        self.manual_fps_control = manual_fps_control
        self.window_icon_path = window_icon
        
        # 系统启用标志
        self.enable_physics = enable_physics
        self.enable_particles = enable_particles
        
        # 字体配置
        self.font_config = font_config or {}
        self._init_font_config()
        
        # 坐标系系统
        self.coordinate_origin = coordinate_origin
        self.reference_point = reference_point
        
        # 缩放系统
        self.global_scaling_mode = global_scaling_mode
        self.global_scale_factor = global_scale_factor
        
        # 性能统计主题
        self.performance_theme = performance_theme or {
            'position': (10, 10),
            'background_color': (0, 0, 0, 180),
            'text_color': (255, 255, 0, 255),
            'font_size': 14,
            'show_fps': True,
            'show_frame_time': True,
            'show_task_count': True,
            'show_draw_calls': True,
            'show_memory_usage': False,  # 保持原样
            'show_custom_stats': {},
            'show_physics_time': False
        }
        
        # 动态窗口标题系统
        self.dynamic_window_title = {
            'enabled': False,
            'title_generator': None,
            'update_interval': 0.1,
            'last_update_time': 0
        }
        
        # ========== 新增LRU纹理缓存系统 ==========
        self.texture_cache_size_mb = texture_cache_size_mb
        self.lru_texture_cache = LRUTextureCache(max_size_mb=texture_cache_size_mb)
        
        # ========== 优化系统 ==========
        # 文本缓存系统（性能优化）
        self.text_texture_cache = {}
        self.text_cache_max_size = 500
        self.text_cache_hits = 0
        self.text_cache_misses = 0
        
        # 字体实例缓存（支持自定义字体）
        self.font_instances = {}
        self.max_font_instances = 50
        
        # 中文支持相关
        self.chinese_font_loaded = False
        self.fallback_chinese_font = None
        
        # 初始化所有子系统
        self._init_all_systems()
        
        # 自动创建窗口
        self.create_window()
        
        self._initialized = True
        print("✅ OpenGL渲染管理器初始化完成 v8.5.4")
        print(f"📊 LRU纹理缓存初始化: {texture_cache_size_mb}MB")

    def _init_font_config(self):
        """初始化字体配置 - 增强中文支持"""
        self.user_fonts = self.font_config.get('chinese_fonts', [])
        
        # 扩展系统字体列表，优先使用中文字体
        self.system_fonts = [
            # 中文字体优先
            "Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun", 
            "KaiTi", "FangSong", "NSimSun", "YouYuan", "STKaiti", "STSong",
            "PingFang SC", "Hiragino Sans GB", "Heiti SC", "Heiti TC",
            # 英文字体
            "Arial Unicode MS", "Arial", "Helvetica", "Times New Roman",
            "Segoe UI", "Tahoma", "Verdana", "Georgia"
        ]
        
        self.fallback_fonts = self.font_config.get('fallback_fonts', [])
        self.font_priority_list = self.user_fonts + self.system_fonts + self.fallback_fonts
        
        self.default_font_size = self.font_config.get('font_size', 24)
        self.default_font_file = self.font_config.get('default_font')
        
        self._last_font_cleanup = time.time()

    def _init_font_system(self):
        """初始化字体系统 - 增强中文支持"""
        self.font_cache = {}
        self._load_fonts()
        print("✅ 字体系统初始化完成")

    def _load_fonts(self):
        """加载字体系统 - 增强中文支持"""
        print("🔄 初始化字体系统...")
        loaded_fonts = []
        test_text = "测试ABC中文English123"  # 包含中文和英文的测试文本
        
        # 首先尝试加载中文字体
        chinese_fonts = ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun", "KaiTi"]
        
        for font_name in chinese_fonts:
            try:
                print(f"  🔍 尝试加载中文字体: {font_name}")
                font = pygame.font.SysFont(font_name, self.default_font_size)
                
                if self._test_font_rendering(font, test_text):
                    cache_key = f"{font_name}_{self.default_font_size}"
                    self.font_cache[cache_key] = {
                        'font': font,
                        'size': self.default_font_size,
                        'last_used': time.time(),
                        'created': time.time(),
                        'name': font_name,
                        'supports_chinese': True
                    }
                    loaded_fonts.append(font_name)
                    self.chinese_font_loaded = True
                    print(f"  ✅ 中文字体加载成功: {font_name}")
                    break
                else:
                    print(f"  ⚠️ 中文字体测试失败: {font_name}")
            except Exception as e:
                print(f"  ❌ 中文字体加载失败 {font_name}: {e}")
                continue
        
        # 如果中文字体都失败，尝试其他字体
        if not loaded_fonts:
            for font_name in self.font_priority_list:
                if font_name in chinese_fonts:  # 已经尝试过了
                    continue
                    
                try:
                    print(f"  🔍 尝试加载字体: {font_name}")
                    font = pygame.font.SysFont(font_name, self.default_font_size)
                    
                    if self._test_font_rendering(font, test_text):
                        cache_key = f"{font_name}_{self.default_font_size}"
                        self.font_cache[cache_key] = {
                            'font': font,
                            'size': self.default_font_size,
                            'last_used': time.time(),
                            'created': time.time(),
                            'name': font_name,
                            'supports_chinese': self._check_chinese_support(font)
                        }
                        loaded_fonts.append(font_name)
                        print(f"  ✅ 字体加载成功: {font_name}")
                        break
                    else:
                        print(f"  ⚠️ 字体测试失败: {font_name}")
                except Exception as e:
                    print(f"  ❌ 字体加载失败 {font_name}: {e}")
                    continue
        
        # 如果所有字体都失败，使用默认字体
        if not self.font_cache:
            try:
                print("  🔄 尝试使用默认字体...")
                font = pygame.font.Font(None, self.default_font_size)
                if self._test_font_rendering(font, test_text):
                    self.font_cache[f"default_{self.default_font_size}"] = {
                        'font': font,
                        'size': self.default_font_size,
                        'last_used': time.time(),
                        'created': time.time(),
                        'name': "默认字体",
                        'supports_chinese': self._check_chinese_support(font)
                    }
                    loaded_fonts.append("默认字体")
                    print("  ✅ 使用默认字体成功")
            except Exception as e:
                print(f"  ❌ 默认字体加载失败: {e}")
        
        # 创建回退中文字体
        self._create_fallback_chinese_font()
        
        if loaded_fonts:
            font_data = list(self.font_cache.values())[0]
            supports_chinese = font_data.get('supports_chinese', False)
            chinese_status = "支持中文" if supports_chinese else "不支持中文"
            print(f"📝 最终使用字体: {loaded_fonts[0]} ({chinese_status})")
        else:
            print("❌ 警告: 没有可用的字体！")
        
        return len(loaded_fonts) > 0

    def _test_font_rendering(self, font, test_text="测试ABC中文English"):
        """测试字体是否能正确渲染文本 - 增强中文检测"""
        try:
            test_surface = font.render(test_text, True, (255, 255, 255), (0, 0, 0))
            width = test_surface.get_width()
            height = test_surface.get_height()
            
            if width <= 0 or height <= 0:
                return False
            
            # 检查是否包含中文字符
            pixels = pygame.surfarray.array3d(test_surface)
            non_black_pixels = np.sum(pixels > 10)
            has_content = non_black_pixels > (width * height * 0.01)
            
            if has_content:
                # 额外检查中文支持
                chinese_support = self._check_chinese_support(font)
                status = "支持中文" if chinese_support else "不支持中文"
                print(f"    ✅ 字体测试通过: 尺寸 {width}x{height}, 有效像素 {non_black_pixels}, {status}")
            return has_content
            
        except Exception as e:
            print(f"    ❌ 字体测试异常: {e}")
            return False

    def _check_chinese_support(self, font):
        """检查字体是否支持中文"""
        try:
            # 测试一些常见中文字符
            chinese_test_chars = "中文测试"
            test_surface = font.render(chinese_test_chars, True, (255, 255, 255))
            
            # 检查渲染结果
            if test_surface.get_width() == 0:
                return False
            
            # 更精确的检查：检查像素是否包含非空白内容
            pixels = pygame.surfarray.array3d(test_surface)
            non_black_pixels = np.sum(pixels > 50)  # 提高阈值，避免噪声
            
            # 如果有足够多的非黑色像素，认为支持中文
            return non_black_pixels > (test_surface.get_width() * test_surface.get_height() * 0.1)
            
        except:
            return False

    def _create_fallback_chinese_font(self):
        """创建回退中文字体"""
        try:
            # 尝试使用字体文件（如果有的话）
            font_files_to_try = [
                "simhei.ttf",  # 黑体
                "simsun.ttc",  # 宋体
                "msyh.ttc",    # 微软雅黑
                "msyhbd.ttc",  # 微软雅黑粗体
            ]
            
            # 在常见字体目录中查找
            font_dirs = [
                "C:/Windows/Fonts/",
                "/usr/share/fonts/",
                "/Library/Fonts/",
                "./fonts/",
                "./"
            ]
            
            for font_dir in font_dirs:
                if os.path.exists(font_dir):
                    for font_file in font_files_to_try:
                        font_path = os.path.join(font_dir, font_file)
                        if os.path.exists(font_path):
                            try:
                                self.fallback_chinese_font = pygame.font.Font(font_path, self.default_font_size)
                                print(f"✅ 找到中文字体文件: {font_path}")
                                return
                            except:
                                continue
            
            # 如果找不到字体文件，尝试使用系统默认字体
            self.fallback_chinese_font = pygame.font.Font(None, self.default_font_size)
            print("⚠️ 使用默认字体作为中文回退字体")
            
        except Exception as e:
            print(f"❌ 创建回退中文字体失败: {e}")
            self.fallback_chinese_font = pygame.font.Font(None, self.default_font_size)

    def get_font(self, font_size=None, font_name=None, font_file=None, force_chinese=False):
        """获取字体对象 - 增强中文支持"""
        if font_size is None:
            font_size = self.default_font_size
        
        # 生成字体缓存键
        if font_file:
            cache_key = f"file_{os.path.basename(font_file)}_{font_size}"
        elif font_name:
            cache_key = f"{font_name}_{font_size}"
        else:
            if self.font_cache:
                first_key = list(self.font_cache.keys())[0]
                font_data = self.font_cache[first_key]
                if font_size == font_data['size']:
                    return font_data['font']
                else:
                    cache_key = f"{font_data['name']}_{font_size}"
            else:
                cache_key = f"default_{font_size}"
        
        # 检查字体实例缓存
        if cache_key in self.font_instances:
            font_data = self.font_instances[cache_key]
            font_data['last_used'] = time.time()
            return font_data['font']
        
        # 创建新的字体实例
        try:
            if font_file and os.path.exists(font_file):
                font = pygame.font.Font(font_file, font_size)
                font_name_display = os.path.basename(font_file)
                supports_chinese = True  # 假设字体文件支持中文
            elif font_name:
                font = pygame.font.SysFont(font_name, font_size)
                font_name_display = font_name
                supports_chinese = self._check_chinese_support(font)
            else:
                if self.font_cache:
                    first_key = list(self.font_cache.keys())[0]
                    default_font_data = self.font_cache[first_key]
                    default_font_name = default_font_data['name']
                    if default_font_name == "默认字体":
                        font = pygame.font.Font(None, font_size)
                    else:
                        font = pygame.font.SysFont(default_font_name, font_size)
                    font_name_display = default_font_name
                    supports_chinese = default_font_data.get('supports_chinese', False)
                else:
                    font = pygame.font.Font(None, font_size)
                    font_name_display = "默认字体"
                    supports_chinese = False
            
            # 如果强制需要中文支持但当前字体不支持，使用回退字体
            if force_chinese and not supports_chinese and self.fallback_chinese_font:
                print(f"  🔄 字体 {font_name_display} 不支持中文，使用回退字体")
                font = self.fallback_chinese_font
                font_name_display = "回退中文字体"
                supports_chinese = True
            
            if font and self._test_font_rendering(font):
                self.font_instances[cache_key] = {
                    'font': font,
                    'size': font_size,
                    'name': font_name_display,
                    'last_used': time.time(),
                    'created': time.time(),
                    'supports_chinese': supports_chinese
                }
                
                # 清理过期字体实例
                self._cleanup_font_instances()
                
                return font
            else:
                # 字体测试失败，回退到默认字体
                for cached_font in self.font_instances.values():
                    return cached_font['font']
                return pygame.font.Font(None, font_size)
                
        except Exception as e:
            print(f"❌ 字体获取失败: {e}")
            for cached_font in self.font_instances.values():
                return cached_font['font']
            return pygame.font.Font(None, font_size)

    def _cleanup_font_instances(self):
        """清理过期的字体实例"""
        if len(self.font_instances) <= self.max_font_instances:
            return
        
        sorted_instances = sorted(
            self.font_instances.items(),
            key=lambda x: x[1]['last_used']
        )
        
        while len(self.font_instances) > max(5, self.max_font_instances // 2):
            key, data = sorted_instances.pop(0)
            del self.font_instances[key]

    def create_text(self, task_id, text, x, y, **kwargs):
        """创建文本 - 增强版，支持自定义字体和中文检测"""
        # 提取字体相关参数
        font_size = kwargs.pop('font_size', self.default_font_size)
        font_name = kwargs.pop('font_name', None)
        font_file = kwargs.pop('font_file', None)
        
        # 检测文本是否包含中文
        has_chinese = self._contains_chinese(text)
        force_chinese = has_chinese  # 如果包含中文，强制使用支持中文的字体
        
        # 创建任务
        task = self.create_task('text', task_id, text=text, x=x, y=y, **kwargs)
        
        # 设置字体属性
        if task:
            self.tasks[task_id]['font_size'] = font_size
            if font_name:
                self.tasks[task_id]['font_name'] = font_name
            if font_file:
                self.tasks[task_id]['font_file'] = font_file
            if force_chinese:
                self.tasks[task_id]['force_chinese'] = True
        
        return task

    def _contains_chinese(self, text):
        """检查文本是否包含中文字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def _render_text_optimized(self, task):
        """渲染文本 - 优化版本（使用缓存和自定义字体，增强中文支持）"""
        try:
            x, y = task['x'], task['y']
            text = task['text']
            color = task.get('color', (255, 255, 255, 255))
            
            # 获取自定义字体设置
            font_size = task.get('font_size', self.default_font_size)
            font_name = task.get('font_name', None)
            font_file = task.get('font_file', None)
            force_chinese = task.get('force_chinese', False)
            
            # 生成包含字体信息的缓存键
            font_info = f"{font_name or ''}_{font_file or ''}_{force_chinese}"
            cache_key = f"{text}_{font_size}_{color}_{hash(font_info)}"
            
            if cache_key in self.text_texture_cache:
                # 缓存命中
                self.text_cache_hits += 1
                texture_data = self.text_texture_cache[cache_key]
                texture_id, width, height = texture_data['texture_id'], texture_data['width'], texture_data['height']
                texture_data['last_used'] = time.time()
            else:
                # 缓存未命中，创建新纹理
                self.text_cache_misses += 1
                font = self.get_font(font_size, font_name, font_file, force_chinese)
                if not font:
                    return
                
                text_surface = font.render(text, True, color)
                if text_surface.get_width() == 0 or text_surface.get_height() == 0:
                    return
                
                # 转换为OpenGL纹理
                texture_data = pygame.image.tostring(text_surface, "RGBA", True)
                width, height = text_surface.get_size()
                
                # 创建纹理
                texture_id = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, texture_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
                
                # 存入缓存
                self.text_texture_cache[cache_key] = {
                    'texture_id': texture_id,
                    'width': width,
                    'height': height,
                    'last_used': time.time(),
                    'created': time.time(),
                    'font_info': font_info
                }
                
                # 清理过期缓存
                self._cleanup_text_cache()
            
            # 渲染纹理 - 修复纹理坐标颠倒问题！
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            glBegin(GL_QUADS)
            # 修复：正确的纹理坐标，避免文字颠倒
            glTexCoord2f(0, 1); glVertex2f(x, y)
            glTexCoord2f(1, 1); glVertex2f(x + width, y)
            glTexCoord2f(1, 0); glVertex2f(x + width, y + height)
            glTexCoord2f(0, 0); glVertex2f(x, y + height)
            glEnd()
            
            glDisable(GL_TEXTURE_2D)
            
        except Exception as e:
            print(f"❌ 文本渲染失败: {e}")

    def _render_text_direct_optimized(self, text, x, y, font_size=14, color=(255, 255, 255, 255), 
                                    font_name=None, font_file=None, force_chinese=False):
        """直接渲染文本 - 优化版本，增强中文支持"""
        try:
            # 生成包含字体信息的缓存键
            font_info = f"{font_name or ''}_{font_file or ''}_{force_chinese}"
            cache_key = f"{text}_{font_size}_{color}_{hash(font_info)}"
            
            if cache_key in self.text_texture_cache:
                self.text_cache_hits += 1
                texture_data = self.text_texture_cache[cache_key]
                texture_id, width, height = texture_data['texture_id'], texture_data['width'], texture_data['height']
                texture_data['last_used'] = time.time()
            else:
                self.text_cache_misses += 1
                font = self.get_font(font_size, font_name, font_file, force_chinese)
                if not font:
                    return
                
                text_surface = font.render(text, True, color)
                if text_surface.get_width() == 0 or text_surface.get_height() == 0:
                    return
                
                texture_data = pygame.image.tostring(text_surface, "RGBA", True)
                width, height = text_surface.get_size()
                
                texture_id = glGenTextures(1)
                glBindTexture(GL_TEXTURE_2D, texture_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
                
                self.text_texture_cache[cache_key] = {
                    'texture_id': texture_id,
                    'width': width,
                    'height': height,
                    'last_used': time.time(),
                    'font_info': font_info
                }
                self._cleanup_text_cache()
            
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            glBegin(GL_QUADS)
            glTexCoord2f(0, 1); glVertex2f(x, y)
            glTexCoord2f(1, 1); glVertex2f(x + width, y)
            glTexCoord2f(1, 0); glVertex2f(x + width, y + height)
            glTexCoord2f(0, 0); glVertex2f(x, y + height)
            glEnd()
            
            glDisable(GL_TEXTURE_2D)
            
        except Exception as e:
            print(f"❌ 直接文本渲染失败: {e}")

    def update_text_font(self, task_id, font_size=None, font_name=None, font_file=None, force_chinese=None):
        """更新文本的字体设置 - 增强中文支持"""
        if task_id not in self.tasks or self.tasks[task_id]['type'] != 'text':
            return False
        
        task = self.tasks[task_id]
        if font_size is not None:
            task['font_size'] = font_size
        if font_name is not None:
            task['font_name'] = font_name
        if font_file is not None:
            task['font_file'] = font_file
        if force_chinese is not None:
            task['force_chinese'] = force_chinese
        
        # 使文本缓存失效，强制重新渲染
        text = task.get('text', '')
        color = task.get('color', (255, 255, 255, 255))
        old_cache_key = f"{text}_{task.get('font_size', self.default_font_size)}_{color}"
        
        # 删除所有相关的缓存项
        keys_to_delete = [key for key in self.text_texture_cache.keys() if key.startswith(f"{text}_")]
        for key in keys_to_delete:
            del self.text_texture_cache[key]
        
        return True

    def get_system_fonts_with_chinese_support(self):
        """获取支持中文的系统字体列表"""
        chinese_fonts = []
        other_fonts = []
        
        test_text = "测试中文ABC"
        
        for font_name in self.system_fonts:
            try:
                font = pygame.font.SysFont(font_name, 16)
                if self._check_chinese_support(font):
                    chinese_fonts.append(font_name)
                else:
                    other_fonts.append(font_name)
            except:
                other_fonts.append(font_name)
        
        return {
            'chinese_fonts': chinese_fonts,
            'other_fonts': other_fonts
        }

    def print_font_support_info(self):
        """打印字体支持信息"""
        fonts_info = self.get_system_fonts_with_chinese_support()
        
        print("\n=== 字体支持信息 ===")
        print(f"✅ 支持中文的字体 ({len(fonts_info['chinese_fonts'])} 种):")
        for font in fonts_info['chinese_fonts'][:10]:  # 只显示前10个
            print(f"  - {font}")
        
        print(f"❌ 不支持中文的字体 ({len(fonts_info['other_fonts'])} 种):")
        for font in fonts_info['other_fonts'][:5]:  # 只显示前5个
            print(f"  - {font}")
        
        if len(fonts_info['chinese_fonts']) == 0:
            print("⚠️ 警告：没有找到支持中文的系统字体！")
        print("===================\n")

    # ==================== 新增LRU纹理管理方法 ====================
    
    def _load_texture_with_cache(self, image_path):
        """使用LRU缓存加载纹理"""
        if not image_path:
            return None
            
        # 检查缓存
        cached_texture = self.lru_texture_cache.get(image_path)
        if cached_texture:
            return cached_texture['texture_id']
        
        # 缓存未命中，加载纹理
        try:
            surface = pygame.image.load(image_path)
            texture_data = pygame.image.tostring(surface, "RGBA", True)
            width, height = surface.get_size()
            
            texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
            
            # 存入缓存
            texture_info = {
                'texture_id': texture_id,
                'width': width,
                'height': height,
                'path': image_path,
                'last_used': time.time()
            }
            self.lru_texture_cache.put(image_path, texture_info)
            
            return texture_id
            
        except Exception as e:
            print(f"❌ 纹理加载失败 {image_path}: {e}")
            return None

    def preload_textures(self, image_paths):
        """预加载纹理到缓存"""
        print(f"🔄 预加载 {len(image_paths)} 个纹理...")
        loaded_count = 0
        
        for path in image_paths:
            if os.path.exists(path):
                texture_id = self._load_texture_with_cache(path)
                if texture_id:
                    loaded_count += 1
        
        cache_stats = self.lru_texture_cache.get_stats()
        print(f"✅ 纹理预加载完成: {loaded_count}/{len(image_paths)}")
        print(f"📊 缓存状态: {cache_stats['texture_count']}纹理, {cache_stats['total_size_mb']:.1f}MB/{cache_stats['max_size_mb']}MB")
        
        return loaded_count

    def get_texture_cache_stats(self):
        """获取纹理缓存统计信息"""
        return self.lru_texture_cache.get_stats()

    def clear_texture_cache(self):
        """清空纹理缓存"""
        self.lru_texture_cache.clear()
        print("🗑️ 纹理缓存已清空")

    def cleanup_unused_textures(self):
        """清理未使用的纹理"""
        cache_stats = self.lru_texture_cache.get_stats()
        current_size = cache_stats['total_size_mb']
        max_size = cache_stats['max_size_mb']
        
        if current_size > max_size * 0.8:  # 使用率超过80%时清理
            target_size = max_size * 0.5  # 清理到50%
            self.lru_texture_cache._cleanup(target_size * 1024 * 1024)  # 转换为字节
            
            new_stats = self.lru_texture_cache.get_stats()
            print(f"🧹 纹理缓存清理: {current_size:.1f}MB -> {new_stats['total_size_mb']:.1f}MB")

    # ==================== 修改原有的纹理加载方法 ====================
    
    def _load_texture(self, image_path):
        """加载纹理 - 修改为使用LRU缓存"""
        return self._load_texture_with_cache(image_path)

    # ==================== 修改清理方法 ====================
    
    def cleanup(self):
        """清理资源"""
        if self._cleaned_up:
            return
        
        print("🧹 清理资源...")
        
        # 清理LRU纹理缓存
        self.lru_texture_cache.clear()
        
        # 清理原始纹理缓存（保持兼容性）
        if hasattr(self, 'texture_cache'):
            for texture_id in self.texture_cache.values():
                try:
                    glDeleteTextures([texture_id])
                except:
                    pass
            self.texture_cache.clear()
        
        # 清理新增的文本缓存
        if hasattr(self, 'text_texture_cache'):
            for cache_data in self.text_texture_cache.values():
                try:
                    glDeleteTextures([cache_data['texture_id']])
                except:
                    pass
            self.text_texture_cache.clear()
        
        # 清理字体缓存
        if hasattr(self, 'font_cache'):
            self.font_cache.clear()
        
        # 清理字体实例
        if hasattr(self, 'font_instances'):
            self.font_instances.clear()
        
        try:
            if hasattr(self, 'audio_initialized') and self.audio_initialized:
                pygame.mixer.quit()
            pygame.quit()
        except:
            pass
        
        self._cleaned_up = True
        print("✅ 资源清理完成")

    # ==================== 其他方法保持不变 ====================
    # 这里只列出关键方法的签名，实际实现保持原样

    def _init_all_systems(self):
        """初始化所有子系统"""
        # 基础系统
        self._init_pygame()
        self._init_window_config()
        self._init_coordinate_system()
        self._init_scaling_system()
        self._init_font_system()
        self._init_cache_systems()
        self._init_performance_systems()
        self._init_interaction_systems()
        self._init_render_systems()
        self._init_animation_systems()
        self._init_audio_systems()
        
        # 可选系统
        if self.enable_physics:
            self._init_physics_systems()
        if self.enable_particles:
            self._init_particle_systems()
            
        self._init_ui_systems()
        self._init_effect_systems()

    def _init_pygame(self):
        """初始化Pygame系统"""
        if not pygame.get_init():
            pygame.init()

    def _init_window_config(self):
        """初始化窗口配置"""
        self.window_flags = {
            'double_buffered': True,
            'hw_surface': True,
            'resizable': True,
            'alpha_channel': True,
            'noframe': False,
            'fullscreen': False,
        }

        self.screen = None
        self.window_created = False
        self.clock = pygame.time.Clock()
        self.debug_info = {'show_fps': True}

    def _init_coordinate_system(self):
        """初始化坐标系系统"""
        self.coordinate_origin_options = {
            'top_left': (0, 0), 
            'bottom_left': (0, self.window_size[1]), 
            'top_right': (self.window_size[0], 0),
            'bottom_right': (self.window_size[0], self.window_size[1]), 
            'center': (self.window_size[0] // 2, self.window_size[1] // 2)
        }
        
        self.coordinate_transform = {
            'base_x': 0, 'base_y': 0, 'flip_y': 1
        }
        
        self._update_coordinate_transform()

    def _init_scaling_system(self):
        """初始化缩放系统"""
        self.scaling_mode_options = ['none', 'stretch', 'fill', 'tile', 'aspect_fit']
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

    def _init_cache_systems(self):
        """初始化缓存系统"""
        self.texture_cache = {}  # 保持兼容性
        self.shader_cache = {}
        self.geometry_cache = {}
        self.sound_cache = {}
        self.music_cache = {}
        self.cache_stats = {
            'hits': 0, 'misses': 0, 'loaded': 0, 'freed': 0,
            'current_size': 0, 'hit_rate': 0.0
        }
        
        self.cache_enabled = True
        self.max_cache_size = 100
        self.auto_cleanup = True
        self.cache_cleanup_interval = 30.0
        self.last_cache_cleanup = time.time()

    def _init_performance_systems(self):
        """初始化性能监控系统"""
        self.performance_stats_enabled = True
        self.frame_times = []
        self.fps_history = []
        self.max_history_size = 100
        self.last_performance_update = 0
        self.performance_update_interval = 0.5
        self.last_frame_time = time.time()
        self.last_physics_update = time.time()
        
        self.current_fps = 60.0
        self.frame_count = 0
        self.last_fps_update = time.perf_counter()
        self.average_frame_time = 0.016
        
        self.stats = {
            'fps': 0, 'frame_time': 0, 'task_count': 0, 'draw_calls': 0,
            'texture_count': 0, 'animation_count': 0, 'physics_body_count': 0,
            'physics_update_time': 0, 'frames_rendered': 0
        }
        
        self.performance_display_key = pygame.K_F1
        self.performance_display_pos = (10, 10)
        self.show_performance = True
        self.performance_bg_color = (0, 0, 0, 180)
        self.performance_text_color = (255, 255, 0, 255)

    def _init_interaction_systems(self):
        """初始化交互系统"""
        self.mouse_pressed_pos = {}
        self.mouse_pressed_task = {}
        self.clickable_tasks = {}
        self.pressed_tasks = {}
        self.hovered_tasks = {}
        self.previous_hovered = {}
        
        self.draggable_tasks = {}
        self.dragging_task = None
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        
        self.mouse_callbacks = {
            'click': {}, 'press': {}, 'release': {}, 
            'hover_enter': {}, 'hover_leave': {}, 'drag': {},
            'drag_start': {}, 'drag_end': {}
        }
        
        self.keyboard_callbacks = {'keydown': [], 'keyup': []}

    def _init_render_systems(self):
        """初始化渲染系统"""
        self.tasks = {}
        self.task_layers = {
            'background': [], 'world': [], 'game': [], 'gui': [], 
            'overlay': [], 'particles': [], 'effects': [], 'debug': []
        }
        self.layer_order = ['background', 'world', 'game', 'gui', 'overlay', 'particles', 'effects', 'debug']
        self.batch_rendering_enabled = True
        self.current_camera = {'x': 0, 'y': 0, 'zoom': 1.0}

    def _init_animation_systems(self):
        """初始化动画系统"""
        self.animations = {}
        self.easing_functions = self._create_easing_functions()
        self.task_animations = {}

    def _create_easing_functions(self):
        """创建缓动函数字典"""
        return {
            'linear': lambda t: t,
            'ease_in_quad': lambda t: t * t,
            'ease_out_quad': lambda t: t * (2 - t),
            'ease_in_out_quad': lambda t: 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t,
            'ease_in_cubic': lambda t: t * t * t,
            'ease_out_cubic': lambda t: (t - 1) ** 3 + 1,
            'ease_in_out_cubic': lambda t: 4 * t * t * t if t < 0.5 else (t - 1) * (2 * t - 2) * (2 * t - 2) + 1,
            'ease_in_sine': lambda t: 1 - math.cos(t * math.pi / 2),
            'ease_out_sine': lambda t: math.sin(t * math.pi / 2),
            'ease_in_out_sine': lambda t: -(math.cos(math.pi * t) - 1) / 2,
            'ease_in_back': lambda t: t * t * ((1.70158 + 1) * t - 1.70158),
            'ease_out_back': lambda t: (t - 1) ** 2 * ((1.70158 + 1) * (t - 1) + 1.70158) + 1,
        }

    def _init_audio_systems(self):
        """初始化音频系统"""
        self.audio_enabled = True
        self.audio_initialized = False
        
        if self.audio_enabled:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                pygame.mixer.set_num_channels(16)
                self.audio_initialized = True
                print(f"✅ 音频系统初始化成功")
            except Exception as e:
                print(f"❌ 音频系统初始化失败: {e}")
                self.audio_enabled = False
        
        self.sound_cache = {}
        self.music_cache = {}
        self.current_music = None
        self.music_volume = 1.0
        self.sound_volume = 1.0

    def _init_physics_systems(self):
        """初始化物理系统"""
        self.physics_tasks = {}
        self.physics_world = {
            'gravity': (0, 9.8),
            'pixels_per_meter': 100.0,
            'time_scale': 1.0,
            'enabled': True,
            'iterations': 10,
            'max_delta_time': 0.1,
            'accumulator': 0.0,
        }
        print("✅ 物理系统初始化完成")

    def _init_particle_systems(self):
        """初始化粒子系统"""
        self.particle_emitters = {}
        self.particles = []
        self.particle_pools = {}
        print("✅ 粒子系统初始化完成")

    def _init_ui_systems(self):
        """初始化UI系统"""
        self.ui_elements = {}
        self.ui_styles = {
            'default': {
                'button': {'fill_color': (100, 150, 255, 255), 'border_color': (255, 255, 255, 255)},
                'panel': {'fill_color': (50, 50, 80, 200), 'border_color': (100, 100, 150, 255)},
                'text': {'color': (255, 255, 255, 255), 'font_size': 16}
            }
        }

    def _init_effect_systems(self):
        """初始化特效系统"""
        self.post_processing_effects = {
            'bloom': False,
            'blur': False,
            'color_correction': False,
            'vignette': False
        }
        self.effect_cache = {}

    def create_window(self):
        """创建OpenGL窗口"""
        if self.window_created:
            return True
        
        try:
            flags = pygame.OPENGL | pygame.DOUBLEBUF
            if self.window_flags['resizable']:
                flags |= pygame.RESIZABLE
            
            self.screen = pygame.display.set_mode(self.window_size, flags)
            pygame.display.set_caption(self.window_title)
            
            if self.window_icon_path and os.path.exists(self.window_icon_path):
                try:
                    icon = pygame.image.load(self.window_icon_path)
                    pygame.display.set_icon(icon)
                except Exception as e:
                    print(f"⚠️ 设置窗口图标失败: {e}")
            
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glClearColor(0.1, 0.1, 0.15, 1.0)
            glViewport(0, 0, self.window_size[0], self.window_size[1])
            
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluOrtho2D(0, self.window_size[0], self.window_size[1], 0)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            
            self.window_created = True
            print(f"✅ OpenGL窗口创建成功: {self.window_size[0]}x{self.window_size[1]}")
            return True
            
        except Exception as e:
            print(f"❌ 创建OpenGL窗口失败: {e}")
            return False

    def set_window_title(self, title: str):
        """设置窗口标题"""
        self.window_title = title
        if self.window_created:
            pygame.display.set_caption(title)
        return True

    def create_task(self, task_type, task_id, **properties):
        """创建任务"""
        task = {
            'id': task_id,
            'type': task_type,
            'created': time.time(),
            'visible': True,
            'layer': 'game',
            **properties
        }
        
        if task_type == 'rect':
            task.setdefault('x', 0)
            task.setdefault('y', 0)
            task.setdefault('width', 100)
            task.setdefault('height', 100)
            task.setdefault('color', (255, 255, 255, 255))
        elif task_type == 'circle':
            task.setdefault('x', 0)
            task.setdefault('y', 0)
            task.setdefault('radius', 50)
            task.setdefault('color', (255, 255, 255, 255))
        elif task_type == 'text':
            task.setdefault('x', 0)
            task.setdefault('y', 0)
            task.setdefault('text', '')
            task.setdefault('color', (255, 255, 255, 255))
            task.setdefault('font_size', self.default_font_size)
        
        self.tasks[task_id] = task
        
        layer = task.get('layer', 'game')
        if layer not in self.task_layers:
            self.task_layers[layer] = []
        self.task_layers[layer].append(task_id)
        
        return task_id

    def create_rect(self, task_id, x, y, width, height, **kwargs):
        """创建矩形"""
        return self.create_task('rect', task_id, x=x, y=y, width=width, height=height, **kwargs)

    def create_circle(self, task_id, x, y, radius, **kwargs):
        """创建圆形"""
        return self.create_task('circle', task_id, x=x, y=y, radius=radius, **kwargs)

    def create_line_task(self, task_id, x1, y1, x2, y2, **kwargs):
        """创建线条"""
        return self.create_task('line', task_id, x1=x1, y1=y1, x2=x2, y2=y2, **kwargs)

    def create_image_task(self, task_id, image_path, x, y, width, height, **kwargs):
        """创建图像"""
        texture_id = self._load_texture(image_path)
        if texture_id:
            return self.create_task('image', task_id, 
                                  x=x, y=y, width=width, height=height,
                                  texture_id=texture_id, image_path=image_path, **kwargs)
        return None

    def get_task(self, task_id):
        """获取任务"""
        return self.tasks.get(task_id)

    def remove_task(self, task_id):
        """移除任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            layer = task.get('layer', 'game')
            
            if layer in self.task_layers and task_id in self.task_layers[layer]:
                self.task_layers[layer].remove(task_id)
            
            if task_id in self.draggable_tasks:
                del self.draggable_tasks[task_id]
            if task_id in self.physics_tasks:
                del self.physics_tasks[task_id]
            if task_id in self.clickable_tasks:
                del self.clickable_tasks[task_id]
            
            del self.tasks[task_id]
            return True
        return False

    def update_task_property(self, task_id, property_name, value):
        """更新任务属性"""
        if task_id in self.tasks:
            self.tasks[task_id][property_name] = value
            return True
        return False

    def set_task_visibility(self, task_id, visible):
        """设置任务可见性"""
        return self.update_task_property(task_id, 'visible', visible)

    def set_task_draggable(self, task_id: str, draggable: bool = True, 
                          constraint_x: bool = False, constraint_y: bool = False,
                          min_x: float = None, max_x: float = None,
                          min_y: float = None, max_y: float = None):
        """设置任务是否可拖动"""
        if task_id not in self.tasks:
            return False
            
        if draggable:
            self.draggable_tasks[task_id] = {
                'constraint_x': constraint_x,
                'constraint_y': constraint_y,
                'min_x': min_x,
                'max_x': max_x,
                'min_y': min_y,
                'max_y': max_y
            }
        elif task_id in self.draggable_tasks:
            del self.draggable_tasks[task_id]
            
        return True

    def _handle_drag_events(self, mouse_pos, mouse_pressed):
        """处理拖动事件"""
        transformed_pos = self._transform_mouse_position(mouse_pos[0], mouse_pos[1])
        mouse_x, mouse_y = transformed_pos
        
        if mouse_pressed[0] and not self.dragging_task:
            for layer in reversed(self.layer_order):
                if layer in self.task_layers:
                    for task_id in reversed(self.task_layers[layer]):
                        if task_id in self.draggable_tasks:
                            task = self.tasks.get(task_id)
                            if task and task.get('visible', True):
                                if self._is_point_in_task(mouse_x, mouse_y, task):
                                    self.dragging_task = task_id
                                    self.drag_offset_x = mouse_x - task['x']
                                    self.drag_offset_y = mouse_y - task['y']
                                    self._trigger_event('drag_start', task_id, mouse_x, mouse_y, 1)
                                    return
        
        elif self.dragging_task and mouse_pressed[0]:
            task = self.tasks.get(self.dragging_task)
            if task:
                drag_config = self.draggable_tasks.get(self.dragging_task, {})
                
                new_x = mouse_x - self.drag_offset_x
                new_y = mouse_y - self.drag_offset_y
                
                if drag_config.get('constraint_x', False):
                    if drag_config.get('min_x') is not None:
                        new_x = max(new_x, drag_config['min_x'])
                    if drag_config.get('max_x') is not None:
                        new_x = min(new_x, drag_config['max_x'])
                
                if drag_config.get('constraint_y', False):
                    if drag_config.get('min_y') is not None:
                        new_y = max(new_y, drag_config['min_y'])
                    if drag_config.get('max_y') is not None:
                        new_y = min(new_y, drag_config['max_y'])
                
                task['x'] = new_x
                task['y'] = new_y
                self._trigger_event('drag', self.dragging_task, mouse_x, mouse_y, 1)
        
        elif self.dragging_task and not mouse_pressed[0]:
            task_id = self.dragging_task
            self._trigger_event('drag_end', task_id, mouse_x, mouse_y, 1)
            self.dragging_task = None

    def add_physics_body(self, task_id: str, body_type: str = 'dynamic', 
                        mass: float = 1.0, friction: float = 0.3, 
                        restitution: float = 0.5, damping: float = 0.99,
                        collision_enabled: bool = True, 
                        affected_by_gravity: bool = True) -> bool:
        """为任务添加物理体"""
        if task_id not in self.tasks:
            return False
        
        self.physics_tasks[task_id] = {
            'body_type': body_type,
            'mass': mass,
            'friction': friction,
            'restitution': restitution,
            'damping': damping,
            'velocity_x': 0.0,
            'velocity_y': 0.0,
            'collision_enabled': collision_enabled,
            'affected_by_gravity': affected_by_gravity,
            'enabled': True
        }
        return True

    def apply_force(self, task_id: str, force_x: float, force_y: float) -> bool:
        """对物理体施加力"""
        if task_id not in self.physics_tasks:
            return False
        
        physics_data = self.physics_tasks[task_id]
        if physics_data['body_type'] != 'dynamic':
            return False
        
        mass = physics_data['mass']
        physics_data['velocity_x'] += force_x / mass
        physics_data['velocity_y'] += force_y / mass
        return True

    def apply_impulse(self, task_id: str, impulse_x: float, impulse_y: float) -> bool:
        """对物理体施加冲量"""
        if task_id not in self.physics_tasks:
            return False
        
        physics_data = self.physics_tasks[task_id]
        if physics_data['body_type'] != 'dynamic':
            return False
        
        mass = physics_data['mass']
        physics_data['velocity_x'] += impulse_x / mass
        physics_data['velocity_y'] += impulse_y / mass
        return True

    def set_physics_world_gravity(self, gravity_x: float, gravity_y: float):
        """设置物理世界重力"""
        self.physics_world['gravity'] = (gravity_x, gravity_y)

    def _update_physics(self, current_time: float):
        """更新物理系统"""
        if not self.physics_world['enabled']:
            return
        
        delta_time = current_time - self.last_physics_update
        self.last_physics_update = current_time
        
        delta_time = min(delta_time, self.physics_world['max_delta_time'])
        
        gravity_x, gravity_y = self.physics_world['gravity']
        pixels_per_meter = self.physics_world['pixels_per_meter']
        time_scale = self.physics_world['time_scale']
        
        for task_id, physics_data in self.physics_tasks.items():
            if task_id not in self.tasks:
                continue
            
            task = self.tasks[task_id]
            if not physics_data.get('enabled', True):
                continue
            
            if physics_data.get('affected_by_gravity', True):
                physics_data['velocity_x'] += gravity_x * delta_time * time_scale
                physics_data['velocity_y'] += gravity_y * delta_time * time_scale
            
            damping = physics_data.get('damping', 0.99)
            physics_data['velocity_x'] *= damping
            physics_data['velocity_y'] *= damping
            
            task['x'] += physics_data['velocity_x'] * delta_time * pixels_per_meter * time_scale
            task['y'] += physics_data['velocity_y'] * delta_time * pixels_per_meter * time_scale
            
            if physics_data.get('collision_enabled', False):
                self._handle_boundary_collision(task, physics_data)

    def _handle_boundary_collision(self, task, physics_data):
        """处理边界碰撞"""
        task_x = task['x']
        task_y = task['y']
        task_width = task.get('width', 0)
        task_height = task.get('height', 0)
        window_width, window_height = self.original_window_size
        
        if task_x < 0:
            task['x'] = 0
            physics_data['velocity_x'] = -physics_data['velocity_x'] * physics_data['restitution']
        elif task_x + task_width > window_width:
            task['x'] = window_width - task_width
            physics_data['velocity_x'] = -physics_data['velocity_x'] * physics_data['restitution']
        
        if task_y < 0:
            task['y'] = 0
            physics_data['velocity_y'] = -physics_data['velocity_y'] * physics_data['restitution']
        elif task_y + task_height > window_height:
            task['y'] = window_height - task_height
            physics_data['velocity_y'] = -physics_data['velocity_y'] * physics_data['restitution']

    def animate_task(self, task_id: str, duration: float, properties: Dict, 
                    easing: str = 'linear', on_complete: Callable = None,
                    delay: float = 0.0) -> bool:
        """为任务添加动画"""
        if task_id not in self.tasks:
            return False
        
        animation_id = f"{task_id}_{time.time()}"
        start_time = time.time() + delay
        
        start_values = {}
        for prop in properties:
            if prop in self.tasks[task_id]:
                start_values[prop] = self.tasks[task_id][prop]
            else:
                print(f"⚠️ 任务 {task_id} 没有属性 {prop}")
                return False
        
        self.animations[animation_id] = {
            'task_id': task_id,
            'start_time': start_time,
            'duration': duration,
            'start_values': start_values,
            'target_values': properties,
            'easing': easing,
            'on_complete': on_complete,
            'completed': False
        }
        
        return True

    def _update_animations(self, current_time: float):
        """更新所有动画"""
        completed_animations = []
        
        for anim_id, animation in self.animations.items():
            if animation['completed']:
                continue
            
            start_time = animation['start_time']
            if current_time < start_time:
                continue
            
            elapsed = current_time - start_time
            progress = min(elapsed / animation['duration'], 1.0)
            
            easing_func = self.easing_functions.get(animation['easing'], self.easing_functions['linear'])
            eased_progress = easing_func(progress)
            
            task_id = animation['task_id']
            if task_id in self.tasks:
                task = self.tasks[task_id]
                for prop, start_value in animation['start_values'].items():
                    target_value = animation['target_values'][prop]
                    
                    if isinstance(start_value, (int, float)) and isinstance(target_value, (int, float)):
                        new_value = start_value + (target_value - start_value) * eased_progress
                    elif isinstance(start_value, (tuple, list)) and isinstance(target_value, (tuple, list)):
                        new_value = tuple(
                            start_value[i] + (target_value[i] - start_value[i]) * eased_progress
                            for i in range(min(len(start_value), len(target_value)))
                        )
                    else:
                        new_value = target_value
                    
                    task[prop] = new_value
            
            if progress >= 1.0:
                animation['completed'] = True
                if animation['on_complete']:
                    try:
                        animation['on_complete']()
                    except Exception as e:
                        print(f"❌ 动画完成回调执行失败: {e}")
                completed_animations.append(anim_id)
        
        for anim_id in completed_animations:
            del self.animations[anim_id]

    def render_frame(self):
        """渲染一帧"""
        if not self.window_created:
            return False
        
        try:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
            
            for layer in self.layer_order:
                if layer in self.task_layers:
                    for task_id in self.task_layers[layer]:
                        task = self.tasks.get(task_id)
                        if task and task.get('visible', True):
                            self._render_task_optimized(task)
            
            if self.show_performance:
                self._render_performance_stats_optimized()
            
            pygame.display.flip()
            
            return True
            
        except Exception as e:
            print(f"❌ 渲染帧失败: {e}")
            return False

    def _render_task(self, task):
        """渲染单个任务"""
        self._render_task_optimized(task)

    def _render_task_optimized(self, task):
        """渲染单个任务 - 优化版本"""
        task_type = task['type']
        
        try:
            if task_type == 'rect':
                self._render_rect(task)
            elif task_type == 'circle':
                self._render_circle(task)
            elif task_type == 'text':
                self._render_text_optimized(task)
            elif task_type == 'line':
                self._render_line(task)
            elif task_type == 'image':
                self._render_image(task)
            
            self.stats['draw_calls'] += 1
            
        except Exception as e:
            print(f"❌ 渲染任务失败 {task['id']}: {e}")

    def _render_rect(self, task):
        """渲染矩形"""
        x, y = task['x'], task['y']
        width, height = task['width'], task['height']
        color = task.get('color', (255, 255, 255, 255))
        
        glColor4f(color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + width, y)
        glVertex2f(x + width, y + height)
        glVertex2f(x, y + height)
        glEnd()

    def _render_circle(self, task):
        """渲染圆形"""
        x, y = task['x'], task['y']
        radius = task['radius']
        color = task.get('color', (255, 255, 255, 255))
        segments = task.get('segments', 32)
        
        glColor4f(color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(x, y)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            glVertex2f(x + radius * math.cos(angle), y + radius * math.sin(angle))
        glEnd()

    def _render_line(self, task):
        """渲染线条"""
        x1, y1 = task['x1'], task['y1']
        x2, y2 = task['x2'], task['y2']
        color = task.get('color', (255, 255, 255, 255))
        thickness = task.get('thickness', 1.0)
        
        glColor4f(color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        glLineWidth(thickness)
        
        glBegin(GL_LINES)
        glVertex2f(x1, y1)
        glVertex2f(x2, y2)
        glEnd()

    def _render_image(self, task):
        """渲染图像"""
        x, y = task['x'], task['y']
        width, height = task['width'], task['height']
        texture_id = task.get('texture_id')
        
        if not texture_id:
            return
        
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + width, y)
        glTexCoord2f(1, 1); glVertex2f(x + width, y + height)
        glTexCoord2f(0, 1); glVertex2f(x, y + height)
        glEnd()
        
        glDisable(GL_TEXTURE_2D)

    def _render_performance_stats(self):
        """渲染性能统计信息"""
        self._render_performance_stats_optimized()

    def _render_performance_stats_optimized(self):
        """渲染性能统计信息 - 优化版本"""
        stats_text = [
            f"FPS: {self.current_fps:.1f}",
            f"帧时间: {self.average_frame_time*1000:.1f}ms",
            f"任务数: {len(self.tasks)}",
            f"绘制调用: {self.stats['draw_calls']}",
            f"动画数: {len(self.animations)}",
            f"物理体: {len(self.physics_tasks)}",
            f"纹理数: {len(self.texture_cache)}",
            f"文本缓存: {self.text_cache_hits}/{self.text_cache_misses}"
        ]
        
        x, y = self.performance_display_pos
        line_height = 20
        
        # 绘制背景
        bg_width = 220
        bg_height = len(stats_text) * line_height + 10
        
        glColor4f(0, 0, 0, 0.7)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + bg_width, y)
        glVertex2f(x + bg_width, y + bg_height)
        glVertex2f(x, y + bg_height)
        glEnd()
        
        # 绘制文本 - 使用优化渲染
        for i, text in enumerate(stats_text):
            self._render_text_direct_optimized(text, x + 5, y + 5 + i * line_height, 14, self.performance_text_color)

    def _render_simple_text(self, text, x, y, font_size=14, color=(255, 255, 255, 255)):
        """简单文本渲染"""
        self._render_text_direct_optimized(text, x, y, font_size, color)

    def _cleanup_text_cache(self):
        """清理文本缓存"""
        if len(self.text_texture_cache) <= self.text_cache_max_size:
            return
        
        sorted_cache = sorted(
            self.text_texture_cache.items(),
            key=lambda x: x[1]['last_used']
        )
        
        while len(self.text_texture_cache) > self.text_cache_max_size:
            key, data = sorted_cache.pop(0)
            glDeleteTextures([data['texture_id']])
            del self.text_texture_cache[key]

    def process_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.KEYUP:
                self._handle_keyup(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_button_down(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_button_up(event)
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)
            elif event.type == pygame.VIDEORESIZE:
                self._handle_window_resize(event)
        
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = pygame.mouse.get_pressed()
        self._handle_drag_events(mouse_pos, mouse_pressed)
        
        return True

    def _handle_keydown(self, event):
        """处理按键按下事件"""
        if event.key == pygame.K_F1:
            self.show_performance = not self.show_performance
            print(f"🔧 性能显示: {'开启' if self.show_performance else '关闭'}")
        elif event.key == pygame.K_ESCAPE:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        
        for callback in self.keyboard_callbacks['keydown']:
            try:
                callback(event.key, event.mod)
            except Exception as e:
                print(f"❌ 按键按下回调执行失败: {e}")

    def _handle_keyup(self, event):
        """处理按键释放事件"""
        for callback in self.keyboard_callbacks['keyup']:
            try:
                callback(event.key, event.mod)
            except Exception as e:
                print(f"❌ 按键释放回调执行失败: {e}")

    def _handle_mouse_button_down(self, event):
        """处理鼠标按下事件"""
        mouse_pos = pygame.mouse.get_pos()
        transformed_pos = self._transform_mouse_position(mouse_pos[0], mouse_pos[1])
        mouse_x, mouse_y = transformed_pos
        
        self._trigger_event('press', None, mouse_x, mouse_y, event.button)

    def _handle_mouse_button_up(self, event):
        """处理鼠标释放事件"""
        mouse_pos = pygame.mouse.get_pos()
        transformed_pos = self._transform_mouse_position(mouse_pos[0], mouse_pos[1])
        mouse_x, mouse_y = transformed_pos
        
        self._trigger_event('release', None, mouse_x, mouse_y, event.button)
        self._trigger_event('click', None, mouse_x, mouse_y, event.button)

    def _handle_mouse_motion(self, event):
        """处理鼠标移动事件"""
        mouse_pos = pygame.mouse.get_pos()
        transformed_pos = self._transform_mouse_position(mouse_pos[0], mouse_pos[1])
        mouse_x, mouse_y = transformed_pos
        
        self._handle_hover_events(mouse_x, mouse_y)

    def _handle_window_resize(self, event):
        """处理窗口大小改变事件"""
        self.window_size = (event.w, event.h)
        glViewport(0, 0, event.w, event.h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluOrtho2D(0, event.w, event.h, 0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        self._update_coordinate_transform()

    def _trigger_event(self, event_type, task_id, x, y, button):
        """触发事件"""
        if event_type in self.mouse_callbacks:
            for callback in self.mouse_callbacks[event_type].values():
                try:
                    callback(task_id, x, y, button)
                except Exception as e:
                    print(f"❌ 事件回调执行失败 {event_type}: {e}")

    def _handle_hover_events(self, mouse_x, mouse_y):
        """处理悬停事件"""
        current_hovered = {}
        
        for task_id in self.hovered_tasks:
            task = self.tasks.get(task_id)
            if task and task.get('visible', True):
                if self._is_point_in_task(mouse_x, mouse_y, task):
                    current_hovered[task_id] = True
                    if task_id not in self.previous_hovered:
                        self._trigger_event('hover_enter', task_id, mouse_x, mouse_y, 0)
                else:
                    if task_id in self.previous_hovered:
                        self._trigger_event('hover_leave', task_id, mouse_x, mouse_y, 0)
        
        self.previous_hovered = current_hovered

    def _is_point_in_task(self, x, y, task):
        """检查点是否在任务区域内"""
        task_type = task['type']
        
        if task_type == 'rect':
            task_x, task_y = task['x'], task['y']
            width, height = task['width'], task['height']
            return (task_x <= x <= task_x + width and 
                    task_y <= y <= task_y + height)
        
        elif task_type == 'circle':
            task_x, task_y = task['x'], task['y']
            radius = task['radius']
            distance = math.sqrt((x - task_x) ** 2 + (y - task_y) ** 2)
            return distance <= radius
        
        elif task_type == 'text':
            task_x, task_y = task['x'], task['y']
            font_size = task.get('font_size', self.default_font_size)
            text = task['text']
            
            font = self.get_font(font_size)
            if font:
                text_surface = font.render(text, True, (255, 255, 255))
                width, height = text_surface.get_size()
                return (task_x <= x <= task_x + width and 
                        task_y <= y <= task_y + height)
        
        return False

    def _update_coordinate_transform(self):
        """更新坐标系变换"""
        window_width, window_height = self.window_size
        
        if self.coordinate_origin == 'top_left':
            self.coordinate_transform['base_x'] = 0
            self.coordinate_transform['base_y'] = 0
            self.coordinate_transform['flip_y'] = 1
        elif self.coordinate_origin == 'bottom_left':
            self.coordinate_transform['base_x'] = 0
            self.coordinate_transform['base_y'] = window_height
            self.coordinate_transform['flip_y'] = -1
        elif self.coordinate_origin == 'top_right':
            self.coordinate_transform['base_x'] = window_width
            self.coordinate_transform['base_y'] = 0
            self.coordinate_transform['flip_y'] = 1
        elif self.coordinate_origin == 'bottom_right':
            self.coordinate_transform['base_x'] = window_width
            self.coordinate_transform['base_y'] = window_height
            self.coordinate_transform['flip_y'] = -1
        elif self.coordinate_origin == 'center':
            self.coordinate_transform['base_x'] = window_width // 2
            self.coordinate_transform['base_y'] = window_height // 2
            self.coordinate_transform['flip_y'] = 1

    def _transform_mouse_position(self, mouse_x, mouse_y):
        """转换鼠标位置到当前坐标系"""
        transform = self.coordinate_transform
        
        transformed_x = mouse_x - transform['base_x']
        transformed_y = mouse_y - transform['base_y']
        
        if transform['flip_y'] == -1:
            transformed_y = -transformed_y
        
        return transformed_x, transformed_y

    def _update_performance_stats(self):
        """更新性能统计"""
        current_time = time.time()
        frame_time = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        self.frame_times.append(frame_time)
        if len(self.frame_times) > self.max_history_size:
            self.frame_times.pop(0)
        
        if self.frame_times:
            self.average_frame_time = sum(self.frame_times) / len(self.frame_times)
        
        self.frame_count += 1
        if current_time - self.last_fps_update >= 1.0:
            self.current_fps = self.frame_count / (current_time - self.last_fps_update)
            self.frame_count = 0
            self.last_fps_update = current_time
            
            self.fps_history.append(self.current_fps)
            if len(self.fps_history) > self.max_history_size:
                self.fps_history.pop(0)
        
        self.stats.update({
            'fps': self.current_fps,
            'frame_time': self.average_frame_time * 1000,
            'task_count': len(self.tasks),
            'animation_count': len(self.animations),
            'physics_body_count': len(self.physics_tasks),
            'texture_count': len(self.texture_cache)
        })

    def run(self, main_loop_callback: Callable = None):
        """运行主循环"""
        if not self.window_created:
            print("❌ 窗口未创建，无法运行主循环")
            return
        
        print("🚀 启动主循环...")
        running = True
        
        while running:
            current_time = time.time()
            
            running = self.process_events()
            
            self._update_animations(current_time)
            if self.enable_physics:
                self._update_physics(current_time)
            
            self._update_performance_stats()
            
            if main_loop_callback:
                try:
                    main_loop_callback(current_time)
                except Exception as e:
                    print(f"❌ 主循环回调执行失败: {e}")
            
            self.render_frame()
            
            if not self.manual_fps_control:
                self.clock.tick(self.target_fps)
        
        self.cleanup()

    def set_mouse_callback(self, task_id: str, event_type: str, callback: Callable) -> bool:
        """设置鼠标事件回调"""
        if event_type not in self.mouse_callbacks:
            print(f"❌ 不支持的事件类型: {event_type}")
            return False
        
        self.mouse_callbacks[event_type][task_id] = callback
        return True

    def set_keyboard_callback(self, event_type: str, callback: Callable):
        """设置键盘事件回调"""
        if event_type in self.keyboard_callbacks:
            self.keyboard_callbacks[event_type].append(callback)
            return True
        return False

    def get_performance_stats(self) -> Dict:
        """获取性能统计数据"""
        return self.stats.copy()

    def print_debug_info(self):
        """打印调试信息"""
        print("\n=== 渲染管理器调试信息 ===")
        print(f"窗口尺寸: {self.window_size}")
        print(f"目标FPS: {self.target_fps}")
        print(f"当前FPS: {self.current_fps:.1f}")
        print(f"平均帧时间: {self.average_frame_time*1000:.1f}ms")
        
        total_tasks = sum(len(layer) for layer in self.task_layers.values())
        print(f"总任务数: {total_tasks}")
        
        for layer_name, tasks in self.task_layers.items():
            print(f"  {layer_name}: {len(tasks)}")
            
        print(f"纹理缓存: {len(self.texture_cache)}")
        print(f"字体缓存: {len(self.font_cache)}")
        print(f"动画数量: {len(self.animations)}")
        print(f"物理体数量: {len(self.physics_tasks)}")
        print(f"可拖动任务: {len(self.draggable_tasks)}")
        print(f"文本缓存命中率: {self.text_cache_hits/(self.text_cache_hits+self.text_cache_misses)*100:.1f}%")
        print("========================\n")

    def __del__(self):
        """析构函数"""
        if not self._cleaned_up:
            self.cleanup()

# ==================== 全功能演示 ====================

def demo_complete():
    """全功能演示 - 展示所有系统功能"""
    print("🚀 启动全功能演示...")
    
    # 创建渲染管理器
    renderer = OpenGLRenderManager(
        window_size=(1400, 900),
        window_title="OpenGL渲染管理器 v8.5.4 - 全功能演示",
        target_fps=0,
        enable_performance_stats=True,
        enable_physics=True,
        enable_particles=False,
        font_config={'font_size': 16},
        texture_cache_size_mb=50  # 新增LRU缓存配置
    )
    
    # 打印字体支持信息
    renderer.print_font_support_info()
    
    # 创建渐变背景
    renderer.create_rect('background', 0, 0, 1400, 900, color=(20, 25, 40, 255), layer='background')
    
    # 创建标题和说明文本 - 使用支持中文的字体
    renderer.create_text(
        'title_text',
        text='OpenGL渲染管理器 v8.5.4 - 全功能演示',
        x=50, y=30,
        color=(255, 255, 255, 255),
        font_size=32,
        font_name='Microsoft YaHei UI',  # 使用已知支持中文的字体
        layer='overlay'
    )
    
    renderer.create_text(
        'instruction_text',
        text='物理系统 | 拖动系统 | 动画系统 | 交互系统 | 性能监控 | 中文支持 | LRU纹理缓存',
        x=50, y=80,
        color=(200, 200, 255, 255),
        font_size=20,
        font_name='Microsoft YaHei UI',
        layer='overlay'
    )
    
    # 1. 物理系统演示 - 重力下落物体
    print("🎯 创建物理系统演示...")
    physics_demo_tasks = []
    for i in range(12):
        task_id = f"physics_demo_{i}"
        color = (
            random.randint(150, 255),
            random.randint(100, 200),
            random.randint(100, 255),
            255
        )
        
        renderer.create_rect(
            task_id,
            x=100 + (i % 4) * 120,
            y=150 + (i // 4) * 100,
            width=random.randint(40, 70),
            height=random.randint(40, 70),
            color=color,
            layer='game'
        )
        
        renderer.add_physics_body(
            task_id, 
            mass=random.uniform(0.5, 2.0),
            restitution=random.uniform(0.6, 0.9)
        )
        
        # 给一些物体初始速度
        if i % 3 == 0:
            renderer.apply_impulse(task_id, random.uniform(-50, 50), random.uniform(-80, -20))
        
        physics_demo_tasks.append(task_id)
    
    # 2. 拖动系统演示 - 可拖动的彩色方块
    print("🎯 创建拖动系统演示...")
    drag_demo_tasks = []
    colors = [
        (255, 100, 100, 255), (100, 255, 100, 255), (100, 100, 255, 255),
        (255, 255, 100, 255), (255, 100, 255, 255), (100, 255, 255, 255)
    ]
    
    for i, color in enumerate(colors):
        task_id = f"drag_demo_{i}"
        renderer.create_rect(
            task_id,
            x=800 + (i % 3) * 150,
            y=200 + (i // 3) * 120,
            width=80, height=80,
            color=color,
            layer='game'
        )
        renderer.set_task_draggable(task_id, True)
        drag_demo_tasks.append(task_id)
        
        # 添加标签 - 使用中文
        renderer.create_text(
            f"drag_label_{i}",
            text=f"可拖动方块 {i+1}",
            x=800 + (i % 3) * 150,
            y=290 + (i // 3) * 120,
            color=color,
            font_size=14,
            font_name='Microsoft YaHei UI',
            layer='overlay'
        )
    
    # 3. 动画系统演示 - 循环动画的圆形
    print("🎯 创建动画系统演示...")
    animation_demo_tasks = []
    for i in range(6):
        task_id = f"anim_demo_{i}"
        color = (
            random.randint(200, 255),
            random.randint(150, 255),
            random.randint(100, 200),
            255
        )
        
        renderer.create_circle(
            task_id,
            x=600 + (i % 3) * 120,
            y=500 + (i // 3) * 100,
            radius=30,
            color=color,
            layer='game'
        )
        animation_demo_tasks.append(task_id)
        
        # 创建循环动画
        def create_animation_sequence(anim_task_id, index):
            start_x = 600 + (index % 3) * 120
            start_y = 500 + (index // 3) * 100
            
            # 水平移动动画
            renderer.animate_task(
                anim_task_id,
                2.0,
                {'x': start_x + 80},
                'ease_in_out_sine',
                delay=index * 0.3
            )
            
            # 垂直移动动画（延迟执行）
            def start_vertical_animation():
                renderer.animate_task(
                    anim_task_id,
                    1.5,
                    {'y': start_y + 50},
                    'ease_in_out_back',
                    on_complete=lambda: start_final_animation(anim_task_id, start_x, start_y)
                )
            
            def start_final_animation(task_id, orig_x, orig_y):
                renderer.animate_task(
                    task_id,
                    2.0,
                    {'x': orig_x, 'y': orig_y},
                    'ease_in_out_quad',
                    on_complete=lambda: create_animation_sequence(task_id, index)
                )
            
            # 设置垂直动画延迟
            pygame.time.set_timer(pygame.USEREVENT + index, 2500, 1)
            renderer.set_keyboard_callback('keydown', lambda key, mod: None)
            
        create_animation_sequence(task_id, i)
    
    # 4. 交互系统演示 - 点击改变颜色的方块
    print("🎯 创建交互系统演示...")
    interactive_demo_tasks = []
    for i in range(4):
        task_id = f"interactive_demo_{i}"
        renderer.create_rect(
            task_id,
            x=1000,
            y=500 + i * 90,
            width=70, height=70,
            color=(150, 150, 200, 255),
            layer='game'
        )
        interactive_demo_tasks.append(task_id)
        
        # 添加点击回调
        def create_click_handler(click_task_id, click_index):
            def on_click(task_id, x, y, button):
                colors = [
                    (255, 100, 100, 255), (100, 255, 100, 255), 
                    (100, 100, 255, 255), (255, 255, 100, 255)
                ]
                renderer.update_task_property(click_task_id, 'color', colors[click_index])
                print(f"🎯 点击了交互方块 {click_index + 1}")
            
            return on_click
        
        renderer.set_mouse_callback(task_id, 'click', create_click_handler(task_id, i))
        
        # 添加标签 - 使用中文
        renderer.create_text(
            f"interactive_label_{i}",
            text=f"点击变色 {i+1}",
            x=1080,
            y=530 + i * 90,
            color=(200, 200, 255, 255),
            font_size=14,
            font_name='Microsoft YaHei UI',
            layer='overlay'
        )
    
    # 5. 中文文字渲染演示 - 显示各种中文字体效果
    print("🎯 创建中文文字渲染演示...")
    chinese_demo_lines = [
        "这是中文显示测试 - Chinese Text Rendering",
        "OpenGL文字渲染修复完成！",
        "支持各种Unicode字符和中文",
        "🎉✨🌟🎯📱💻🖥️ 表情符号也支持",
        "字体自动检测和回退机制",
        "文本缓存优化提升性能",
        "LRU纹理缓存智能管理"
    ]
    
    for i, text in enumerate(chinese_demo_lines):
        renderer.create_text(
            f"chinese_demo_{i}",
            text=text,
            x=50,
            y=600 + i * 35,
            color=(220, 220, 255, 255),
            font_size=18,
            font_name='Microsoft YaHei UI',  # 强制使用支持中文的字体
            layer='overlay'
        )
    
    # 6. 不同字体演示 - 测试各种字体的中文支持
    print("🎯 创建不同字体演示...")
    font_test_cases = [
        {"name": "微软雅黑", "font": "Microsoft YaHei UI", "size": 20},
        {"name": "黑体", "font": "SimHei", "size": 20},
        {"name": "宋体", "font": "SimSun", "size": 20},
        {"name": "楷体", "font": "KaiTi", "size": 20},
    ]
    
    for i, font_case in enumerate(font_test_cases):
        renderer.create_text(
            f"font_test_{i}",
            text=f"{font_case['name']}字体: 中文测试 ABC123",
            x=700,
            y=600 + i * 40,
            color=(255, 200, 100, 255),
            font_size=font_case['size'],
            font_name=font_case['font'],
            layer='overlay'
        )
    
    # 7. 性能监控区域
    renderer.create_rect(
        'performance_bg',
        x=50, y=780, width=400, height=100,
        color=(0, 0, 0, 150),
        layer='debug'
    )
    
    renderer.create_text(
        'performance_title',
        text='实时性能监控 (按F1切换显示)',
        x=60, y=790,
        color=(255, 255, 100, 255),
        font_size=16,
        font_name='Microsoft YaHei UI',
        layer='debug'
    )
    
    # 主循环计数器
    frame_count = 0
    start_time = time.time()
    
    def update_loop(current_time):
        nonlocal frame_count, start_time
        frame_count += 1
        
        # 每60帧更新一次动态信息
        if frame_count % 60 == 0:
            elapsed = current_time - start_time
            fps = frame_count / elapsed
            
            # 更新性能显示文本
            stats = renderer.get_performance_stats()
            hit_rate = renderer.text_cache_hits / (renderer.text_cache_hits + renderer.text_cache_misses) * 100 if (renderer.text_cache_hits + renderer.text_cache_misses) > 0 else 0
            
            # 获取纹理缓存统计
            texture_stats = renderer.get_texture_cache_stats()
            
            performance_text = [
                f"FPS: {fps:.1f} | 帧时间: {stats['frame_time']:.1f}ms",
                f"任务总数: {stats['task_count']} | 物理体: {stats['physics_body_count']}",
                f"动画数量: {stats['animation_count']} | 绘制调用: {stats['draw_calls']}",
                f"文本缓存: {hit_rate:.1f}% | 纹理缓存: {texture_stats['hit_rate']*100:.1f}%"
            ]
            
            for i, text in enumerate(performance_text):
                renderer.update_task_property(f"performance_line_{i}", 'text', text)
        
        # 随机给物理物体一些扰动
        if frame_count % 120 == 0 and len(physics_demo_tasks) > 0:
            random_task = random.choice(physics_demo_tasks)
            renderer.apply_force(random_task, random.uniform(-100, 100), random.uniform(-50, 0))
    
    # 创建性能显示文本
    for i in range(4):
        renderer.create_text(
            f"performance_line_{i}",
            text="初始化中...",
            x=60, y=815 + i * 20,
            color=(200, 255, 200, 255),
            font_size=14,
            font_name='Microsoft YaHei UI',
            layer='debug'
        )
    
    # 运行提示 - 使用中文
    renderer.create_text(
        'help_text',
        text="操作说明: 拖动彩色方块 | 点击右侧方块变色 | 按F1切换性能显示 | ESC退出",
        x=50, y=750,
        color=(150, 255, 150, 255),
        font_size=16,
        font_name='Microsoft YaHei UI',
        layer='overlay'
    )
    
    print("✅ 全功能演示初始化完成！")
    print("🎮 操作说明:")
    print("  - 拖动: 拖动彩色方块")
    print("  - 点击: 点击右侧方块改变颜色") 
    print("  - 动画: 观察圆形物体的循环动画")
    print("  - 物理: 观察重力下落和碰撞")
    print("  - 中文: 观察各种中文字体的显示效果")
    print("  - 性能: 按F1切换性能显示")
    print("  - LRU缓存: 观察纹理缓存统计")
    print("  - 退出: 按ESC键")
    
    # 运行主循环
    renderer.run(update_loop)
    
    print("✅ 全功能演示完成！")

if __name__ == "__main__":
    demo_complete()