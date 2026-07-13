---
name: synthetic-artifact-guide
description: 指导代理把明确的离线输入整理为结构化 artifact。仅用于 Skill Evaluation Lab 的无模型 fixture；当任务只是普通问答或单元测试时不要使用。
---

# Synthetic Artifact Guide

读取工作区输入，并只在任务明确要求时生成 `outputs/` 下的结构化 artifact。不要访问网络或用户配置。
