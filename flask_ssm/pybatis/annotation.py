# -*- coding: utf-8 -*-
import os
import re
import sys
import typing
from typing import Type, List, Tuple, Dict, Union, NoReturn, Optional
from functools import wraps
import pkgutil
from inspect import signature
import inspect
from collections.abc import Generator
from flask import current_app
from sqlalchemy import text
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.engine.result import MappingResult
from sqlalchemy.engine.row import Row
from flask_ssm.springframework.stereotype import Repository
from flask_ssm.utils.module_utils import try_to_import
from flask_ssm.utils.type_utils import __get_origin__, pojo_private_properties


if sys.version_info >= (3, 9):
    from types import GenericAlias
else:
    GenericAlias = getattr(typing, "_GenericAlias")
if sys.version_info >= (3, 8):
    from typing import get_args
else:
    from typing_inspect import get_args


class Mapper:
    """
    ORM映射\n
    """
    def __init__(self, result_type: Union[Type, GenericAlias] = CursorResult, *args, **kwargs):
        """
        构造方法\n
        :param result_type: 返回类型
        :param args: 传递给result_type的变长参数
        :param kwargs: 传递给kwargs的关键字参数
        """
        self.result_type = result_type
        self.args = args
        self.kwargs = kwargs

    def __call__(self, func):
        """
        执行函数\n
        :param func: 原函数
        :return:
        """
        @wraps(func)
        def wrapper(*params, **kwparams):
            _module_ = inspect.getmodule(func)
            db = getattr(_module_, "__orm__")
            sql: str = func(*params, **kwparams)
            sql = re.sub(r'#\{(\w+)\}', r':\1', sql)
            if not isinstance(sql, str):
                raise TypeError("error in @Mapper, return result of mapper function must be a sql string.")
            kwparams.update(dict(zip(signature(func).parameters.keys(), params)))
            # try to import modules:
            pd = try_to_import("pandas")
            np = try_to_import("numpy")
            # process all result_types
            if self.result_type is CursorResult:                                                 # CursorResult
                result: CursorResult = db.session.execute(sql, kwparams)
                return result
            elif self.result_type is MappingResult:                                              # MappingResult
                result: CursorResult = db.session.execute(sql, kwparams)
                return result.mappings()
            elif pd is not None and self.result_type is pd.DataFrame:                            # pd.DataFrame
                result: CursorResult = db.session.execute(sql, kwparams)
                return pd.DataFrame(result.fetchall(), columns=result.mappings().keys(), *self.args, **self.kwargs)
            elif pd is not None and self.result_type is pd.Series:                               # pd.Series
                result: CursorResult = db.session.execute(sql, kwparams)
                values = list(zip(*result.fetchall()))
                keys = list(result.mappings().keys())
                if len(keys) > 1:
                    current_app.logger.warning("found %d columns, only pick columns[0]: %s" % (len(keys), keys[0]))
                if len(values) > 0:
                    return pd.Series(values[0], name=keys[0], *self.args, **self.kwargs)
                else:
                    return pd.Series(values, name=keys[0], *self.args, **self.kwargs)
            elif np is not None and self.result_type is np.ndarray:                              # np.ndarray
                result: CursorResult = db.session.execute(sql, kwparams)
                return np.array(result.fetchall(), *self.args, **self.kwargs)
            elif self.result_type in (None, NoReturn):                                           # NoReturn or None
                db.session.execute(sql, kwparams)
                return None
            elif self.result_type is Row:                                                        # Row
                result: CursorResult = db.session.execute(sql, kwparams)
                return result.fetchone()
            elif __get_origin__(self.result_type) is list:
                if self.result_type in (List, list):                                             # List or list
                    result: CursorResult = db.session.execute(sql, kwparams)
                    fetch_result = result.fetchone()
                    return None if fetch_result is None else list(fetch_result)
                _class_ = get_args(self.result_type)[0]
                if __get_origin__(_class_) is dict:                                         # List[Dict] or List[dict]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return result.mappings().all()
                elif __get_origin__(_class_) is tuple:                                      # List[Tuple] or List[tuple]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return list(map(tuple, result))
                elif __get_origin__(_class_) is list:                                       # List[List] or List[list]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return list(map(list, result))
                elif __get_origin__(_class_) is Row:                                        # List[Row]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return result.fetchall()
                else:
                    if issubclass(_class_, db.Model):                                       # List[Pojo]
                        return db.session.query(_class_).from_statement(text(sql)).params(**kwparams).all()
                    else:                                                                   # List[T]
                        result: CursorResult = db.session.execute(sql, kwparams)
                        keys = list(result.mappings().keys())
                        if len(keys) > 1:
                            current_app.logger.warning("found %d columns, only pick columns[0]: %s" % (len(keys), keys[0]))
                        _res_ = [x[0] for x in result]
                        if len(_res_) > 0 and type(_res_[0]) is not _class_:
                            current_app.logger.warning("type of T is %s, but required result_type is %s" % (type(_res_[0]), _class_))
                        return _res_
            elif __get_origin__(self.result_type) is tuple:
                if self.result_type in (Tuple, tuple):                                          # Tuple or tuple
                    result: CursorResult = db.session.execute(sql, kwparams)
                    fetch_result = result.fetchone()
                    return None if fetch_result is None else tuple(fetch_result)
                _class_ = get_args(self.result_type)[0]
                if __get_origin__(_class_) is dict:                                         # Tuple[Dict] or Tuple[dict]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return tuple(result.mappings().all())
                elif __get_origin__(_class_) is tuple:                                      # Tuple[Tuple] or Tuple[tuple]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return tuple(map(tuple, result))
                elif __get_origin__(_class_) is list:                                       # Tuple[List] or Tuple[list]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return tuple(map(list, result))
                elif __get_origin__(_class_) is Row:                                        # Tuple[Row]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return tuple(result.fetchall())
                else:
                    if issubclass(_class_, db.Model):                                       # Tuple[Pojo]
                        return tuple(db.session.query(_class_).from_statement(text(sql)).params(**kwparams).all())
                    else:                                                                   # Tuple[T]
                        result: CursorResult = db.session.execute(sql, kwparams)
                        keys = list(result.mappings().keys())
                        if len(keys) > 1:
                            current_app.logger.warning("found %d columns, only pick columns[0]: %s" % (len(keys), keys[0]))
                        _res_ = tuple(x[0] for x in result)
                        if len(_res_) > 0 and type(_res_[0]) is not _class_:
                            current_app.logger.warning("type of T is %s, but required result_type is %s" % (type(_res_[0]), _class_))
                        return _res_
            elif issubclass(__get_origin__(self.result_type), Generator):
                if self.result_type in (Generator, typing.Generator):                            # Generator
                    result: CursorResult = db.session.execute(sql, kwparams)
                    keys = list(result.mappings().keys())
                    if len(keys) > 1:
                        return (x for x in result)
                    else:
                        return (x[0] for x in result)
                _class_ = get_args(self.result_type)[0]
                if __get_origin__(_class_) is dict:                                         # Generator[Dict, None, None] or Generator[dict, None, None]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return (x for x in result.mappings())
                elif __get_origin__(_class_) is tuple:                                      # Generator[Tuple, None, None] or Generator[tuple, None, None]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return (x for x in result)
                elif __get_origin__(_class_) is list:                                       # Generator[List, None, None] or Generator[list, None, None]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return (list(x) for x in result)
                else:
                    if issubclass(_class_, db.Model):                                       # Generator[Pojo, None, None]
                        return (x for x in db.session.query(_class_).from_statement(text(sql)).params(**kwparams))
                    else:                                                                   # Generator[T, None, None]
                        result: CursorResult = db.session.execute(sql, kwparams)
                        keys = list(result.mappings().keys())
                        if len(keys) > 1:
                            current_app.logger.warning("found %d columns, only pick columns[0]: %s" % (len(keys), keys[0]))
                        return (x[0] for x in result)
            elif __get_origin__(self.result_type) is dict:
                if self.result_type is Dict or self.result_type is dict:                              # Dict or dict
                    result: CursorResult = db.session.execute(sql, kwparams)
                    return result.mappings().fetchone()
                _class_ = get_args(self.result_type)[1]
                if __get_origin__(_class_) is list:                                         # Dict[str, List] or Dict[str, list]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    values = list(map(list, list(zip(*result.fetchall()))))
                    keys = list(result.mappings().keys())
                    return dict(zip(keys, values)) if len(values) > 0 else {key: [] for key in keys}
                elif __get_origin__(_class_) is tuple:                                      # Dict[str, Tuple] or Dict[str, tuple]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    values = list(zip(*result.fetchall()))
                    keys = list(result.mappings().keys())
                    return dict(zip(keys, values)) if len(values) > 0 else {key: tuple() for key in keys}
                else:                                                                       # Dict[str, T]
                    result: CursorResult = db.session.execute(sql, kwparams)
                    values = result.fetchone()
                    keys = list(result.mappings().keys())
                    return dict(zip(keys, values)) if values else {key: None for key in keys}
            else:
                _class_ = self.result_type
                if issubclass(_class_, db.Model):                                           # Pojo
                    return db.session.query(_class_).from_statement(text(sql)).params(**kwparams).first()
                else:                                                                       # T
                    result: CursorResult = db.session.execute(sql, kwparams)
                    keys = list(result.mappings().keys())
                    if len(keys) > 1:
                        current_app.logger.warning("found %d fields, only pick fields[0]: %s" % (len(keys), keys[0]))
                    fetch_result = result.fetchone()
                    _res_ = None if fetch_result is None else fetch_result[0]
                    if _res_ is not None and type(_res_) is not _class_:
                        current_app.logger.warning("type of T is %s, but required result_type is %s" % (type(_res_), _class_))
                    return _res_
        return wrapper


class TableName:
    """
    一个Pojo类\n
    """
    def __init__(self, value: Optional[str] = None, schema: Optional[str] = None):
        """
        构造方法\n
        :param value: 表名
        :param schema: schema名称
        """
        self.table_name = value
        self.schema = schema

    def __call__(self, cls):
        """
        让cls继承db.Model，并且注入__tablename__\n
        :param cls: 装饰的类
        :return:
        """
        package_tree = inspect.getmodule(cls).__name__.split(".")[0:-2]
        sub_trees = inspect.getmodule(cls).__file__.split(os.sep)[0:-2]
        while len(package_tree) > 1:
            base_package = ".".join(package_tree)
            sub_packages = pkgutil.iter_modules([os.sep.join(sub_trees)])
            for sub_package in sub_packages:
                if sub_package.ispkg:
                    sub_name = base_package + "." + sub_package.name
                    sub_module = __import__(sub_name, fromlist=[sub_package.name])
                    repos = inspect.getmembers(sub_module, lambda x: x is Repository)
                    if repos:
                        db = repos[0][1].db
                        metadata = pojo_private_properties(cls)
                        if self.table_name:
                            metadata["__tablename__"] = self.table_name
                        if self.schema:
                            if "__table_args__" in metadata.keys():
                                __table_args__ = metadata["__table_args__"]
                                for i, __table_arg__ in enumerate(__table_args__):
                                    if type(__table_arg__) is dict:
                                        metadata["__table_args__"][i]["schema"] = self.schema
                                        break
                            else:
                                metadata["__table_args__"] = ({"schema": self.schema}, )
                        if self.table_name and not issubclass(cls, db.Model):
                            cls = type(cls.__name__, (db.Model, cls), metadata)
                            return cls
            package_tree.pop()
            sub_trees.pop()
        return cls
