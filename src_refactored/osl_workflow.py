"""
OptiSLang 雙節點工作流編排 (AMOP 靈敏度 -> OCO 最佳化 -> DesignExport)。

最大改動：原本 AMOP 與 OCO(Direct) 兩段近乎相同的
register/range/criteria 程式碼，抽成 _configure_python_node() 共用，
消除「改一邊忘了改另一邊」的風險，並把所有 except:pass 換成 log 回報。
"""
import os

from ansys.optislang.core import Optislang
import ansys.optislang.core.node_types as node_types
from ansys.optislang.core.nodes import DesignFlow
from ansys.optislang.core.project_parametric import ComparisonType, ObjectiveCriterion

import config
import objective as obj_mod
from param_utils import strip_unit, resolve_range, osl_initial_value, py_name

_DIRECTION = {"MIN": ComparisonType.MIN, "MAX": ComparisonType.MAX}


def _add_objective(node, spec):
    name, expression, direction_str = obj_mod.objective(spec)
    node.criteria_manager.add_criterion(
        ObjectiveCriterion(name=name, expression=expression, criterion=_DIRECTION[direction_str]))


def _set_python_path(py_node, script_path):
    prop = py_node.get_property("Path")
    prop["path"]["split_path"]["head"] = os.path.dirname(script_path)
    prop["path"]["split_path"]["tail"] = os.path.basename(script_path)
    py_node.set_property("Path", prop)


def _configure_python_node(node, script_path, selected, spec, log):
    """
    在 node 底下建立 Python2 子節點，註冊參數/響應、設定範圍與目標。
    AMOP 與 Direct-OCO 共用同一套邏輯。響應與目標依 objective spec 決定。
    """
    py_node = node.create_node(node_types.Python2, design_flow=DesignFlow.RECEIVE_SEND)
    _set_python_path(py_node, script_path)

    # 註冊參數與響應
    for name, value, _mn, _mx, ptype in selected:
        try:
            iv = strip_unit(value)
        except ValueError:
            iv = 0.0
        py_node.register_location_as_parameter(py_name(name), py_name(name), osl_initial_value(iv, ptype))
    for resp_name, resp_init in obj_mod.response_registrations(spec):
        py_node.register_location_as_response(resp_name, resp_name, resp_init)

    # 設定參數範圍
    param_map = {p.name: p for p in node.parameter_manager.get_parameters()}
    for name, value, mn, mx, _ptype in selected:
        p = param_map.get(py_name(name))
        if p is None:
            log(f"[警告] 參數 {name} 未在 {node.get_name()} 找到，略過範圍設定")
            continue
        try:
            iv = strip_unit(value)
            fmn, fmx = resolve_range(iv, mn, mx)
            p.range = [fmn, fmx]
            p.reference_value = (fmn + fmx) / 2.0
            node.parameter_manager.modify_parameter(p)
        except Exception as e:
            log(f"[警告] 設定 {name} 範圍失敗: {e}")

    _add_objective(node, spec)
    return py_node


def _resolve_executable(osl_ver):
    """找 optislang.exe 實體路徑，避免環境變數遺失。"""
    if not osl_ver:
        return None
    for base in config.OSL_INSTALL_BASES:
        path = rf"{base}{osl_ver}\optiSlang\optislang.exe"
        if os.path.exists(path):
            return path
    return None


def build_workflow(*, selected, spec, oco_mode, max_eval,
                   version_key, script_path, opf_path, do_start, log):
    """
    建立並儲存雙節點 .opf。selected = [(name, value, min, max, type), ...]。
    spec 為 objective spec（眼圖或 S 參數）。
    log 為 callable(str)，所有錯誤都會回報而非靜默吞掉。
    """
    osl_ver = config.AEDT_VERSIONS.get(version_key)
    kwargs = {"ini_timeout": config.OSL_INI_TIMEOUT}
    exe_path = _resolve_executable(osl_ver)
    if exe_path:
        kwargs["executable"] = exe_path
    elif osl_ver:
        kwargs["version"] = osl_ver

    log(f"[系統] 嘗試啟動 OptiSLang (參數: {kwargs})")
    with Optislang(**kwargs) as osl:
        root = osl.application.project.root_system
        amop = root.create_node(node_types.AMOP)
        opt = root.create_node(node_types.OCO)
        dexp = root.create_node(node_types.DesignExport)

        amop.get_output_slots(name="OBestDesigns")[0].connect_to(
            opt.get_input_slots(name="IStartDesigns")[0])
        opt.get_output_slots(name="ODesigns")[0].connect_to(
            dexp.get_input_slots(name="IDesigns")[0])

        # AMOP 靈敏度節點
        _configure_python_node(amop, script_path, selected, spec, log)

        # OCO 最佳化節點
        if oco_mode == "Direct":
            _configure_python_node(opt, script_path, selected, spec, log)
        else:
            # MOP 虛擬求解
            mop_node = opt.create_node(node_types.Mopsolver, design_flow=DesignFlow.RECEIVE_SEND)
            for p in amop.parameter_manager.get_parameters():
                try:
                    opt.parameter_manager.add_parameter(p)
                except Exception as e:
                    log(f"[警告] 複製參數到 OCO 失敗: {e}")
            try:
                amop.get_output_slots(name="OMDBPath")[0].connect_to(
                    mop_node.get_input_slots(name="IMDBPath")[0])
            except Exception as e:
                log(f"MOP 接線失敗: {e}")
            _add_objective(opt, spec)

        # AMOP 取樣數
        try:
            info = amop.get_property("AMopSettings")
            info["num_designs_max"] = max_eval
            amop.set_property("AMopSettings", info)
        except Exception as e:
            log(f"[警告] 設定 AMOP 取樣數失敗: {e}")

        osl.application.save_as(opf_path)
        log(f"[層2] 專案已儲存: {opf_path}")
        if do_start:
            log("正在啟動雙節點工作流計算...")
            osl.application.project.start()
