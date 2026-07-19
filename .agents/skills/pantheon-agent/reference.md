# Reference — Pantheon agent & skill internals

## `BaseAgent` contract (`agents/base.py`)

```python
@dataclass
class AgentTask:
    task_type: str
    description: str
    input: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentResult:
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    thinking_process: str = ""
    execution_log: str = ""
    error: Optional[str] = None

class BaseAgent(ABC):
    def __init__(self, specialist: SpecialistAgent): ...
    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult: ...
    async def safe_run(self, task: AgentTask) -> AgentResult: ...   # wraps run() with handle_run_error
    def apply_skills_to_prompt(self, base_prompt: str) -> str: ...   # injects skill personas
    def get_skill_tags(self) -> List[str]: ...                       # knowledge-search tags
    @property
    def name(self) -> str: ...                                       # = self.specialist.name
    @property
    def skills(self) -> List[AgentSkill]: ...
```

- Subclasses implement `run()`; callers use `safe_run()` for standardized error results.
- Build the system prompt as `self.apply_skills_to_prompt(BASE_PROMPT)` so the agent's 2–3 skills
  inject their personas (pulled from `skills/*.yaml`).
- `_enrich_with_knowledge` / `_save_execution_knowledge` provide the knowledge loop (see base.py).

## `AgentSkill` enum (`core/models/organization.py`)

`class AgentSkill(str, Enum)` — current members (snake_case values, one per `skills/<value>.yaml`):
`strategic_planning, corporate_research, org_design, agent_workflow_design, prompt_engineering,
tool_integration, deep_research, performance_analysis, knowledge_curation, codebase_exploration`.

`SpecialistAgent.skills: List[AgentSkill] = Field(..., min_length=2, max_length=3)`.

## Skill YAML schema (`skills/<id>.yaml`)

```yaml
schema_version: "1.0"
id: deep_research            # MUST equal the AgentSkill enum value
name: Deep Research
description: 技術調査・根本原因分析・詳細調査
persona: |
  あなたは…の専門家です。           # becomes the persona line
focus: |
  …どう取り組むか…
output_hint: |
  …どんな出力を返すか…
tags:                        # knowledge-search tags
  - research
  - analysis
```

The loader (`core/loaders/skill_loader.get_skill_loader().get(id)`) returns a `SkillDefinition`
whose `.to_prompt_addon()` (persona + focus + output_hint) is injected by `AgentSkillEngine`.

## Skill-engine flow (`core/intelligence/agent_skill_engine.py`)

`apply_skills_to_prompt(base_prompt, skills)` → for each skill, `_get_skill_section()` loads the
YAML addon and wraps everything in a `===【あなたの専門スキル】===` block appended to the base prompt.
There is **no** hardcoded `SKILL_DEFINITIONS` dict — everything flows from `skills/*.yaml`.
