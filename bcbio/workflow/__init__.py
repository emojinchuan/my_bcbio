from bcbio.workflow import template

workflows = {
    "template": template
}

def setup(name, inputs):
    workflow = workflows[name]
    args = workflow.parse_args(inputs)
    return workflow.setup(args)
